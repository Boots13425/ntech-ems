"""Campaign validation and plain-text personalization. No expression evaluation or HTML."""
import re
from datetime import timedelta
from email.utils import make_msgid
from email_validator import validate_email, EmailNotValidError

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from uuid import UUID
from sqlalchemy import select, update

from app.models import (EmailCampaign, CampaignRecipient, OutboundEmail, EmailSuppression,
                        EmailConfiguration, Contact, User, utcnow)

VARIABLES = ('contact_name', 'contact_position', 'company_name', 'industry', 'country',
             'sender_name', 'sender_title', 'company_website')


class Content(BaseModel):
    model_config = ConfigDict(extra='forbid')
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=50000)

    @field_validator('subject')
    @classmethod
    def subject_header(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('Subject cannot contain control characters')
        return value


class Step(Content):
    days: int = Field(ge=1, le=365, strict=True)


class TemplateInput(Content):
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=60)
    status: Literal['active', 'archived'] = 'active'


class CampaignInput(Content):
    name: str = Field(min_length=1, max_length=150)
    objective: Literal['Partnership', 'Customer Acquisition', 'General Outreach']
    description: str = Field(default='', max_length=5000)
    contact_ids: list[UUID] = Field(min_length=1, max_length=500)
    steps: list[Step] = Field(default_factory=list, max_length=3)
    version: int | None = None


def render(value, variables):
    missing = set()
    def replace(match):
        key = match.group(1).strip()
        result = variables.get(key) if key in VARIABLES else None
        if not result:
            missing.add(key)
            return match.group(0)
        return str(result)
    rendered = re.sub(r'\{\{([^{}]*)\}\}', replace, value)
    if '{{' in rendered or '}}' in rendered:
        missing.add('unresolved variable')
    return rendered, sorted(missing)


def variables_for(contact, sender):
    org = contact.organization
    return dict(contact_name=contact.full_name, contact_position=contact.job_title,
                company_name=org.name, industry=org.industry, country=org.country,
                company_website=org.website, sender_name=sender.full_name,
                sender_title=', '.join(r.name for r in sender.responsibilities) or ', '.join(r.name for r in sender.roles))


def recipients(db, campaign):
    return list(db.scalars(select(CampaignRecipient).where(CampaignRecipient.campaign_id == campaign.id)))


def suppressed(db, email):
    return db.scalar(select(EmailSuppression.id).where(EmailSuppression.email == email)) is not None


def valid_address(email):
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def validate_campaign(db, campaign):
    rows = recipients(db, campaign)
    if not rows:
        raise HTTPException(422, 'Select at least one recipient')
    for recipient in rows:
        if not valid_address(recipient.email):
            raise HTTPException(422, 'A selected contact has an invalid email address')
        contact = db.get(Contact, recipient.contact_id) if recipient.contact_id else None
        if not contact or contact.organization.is_archived or contact.email != recipient.email:
            raise HTTPException(409, 'A selected contact changed or is unavailable. Edit and review the draft.')
        if suppressed(db, recipient.email):
            raise HTTPException(409, 'A selected recipient is suppressed. Remove them before approval.')
        for content in [dict(subject=campaign.subject, body=campaign.body), *campaign.steps]:
            for key in ('subject', 'body'):
                result, missing = render(content[key], recipient.variables)
                if missing:
                    raise HTTPException(422, 'Missing personalization: ' + ', '.join(missing))
                if key == 'subject' and (len(result) > 500 or '\r' in result or '\n' in result):
                    raise HTTPException(422, 'Personalized subject is invalid')
    return rows


def sender_configuration(db):
    row = db.get(EmailConfiguration, 1)
    if not row or not row.username_encrypted or not row.password_encrypted or row.security == 'none':
        raise HTTPException(409, 'The CEO must save authenticated TLS SMTP settings before launching campaigns')
    return row


def queue_message(db, campaign, recipient, step, due_at):
    content = dict(subject=campaign.subject, body=campaign.body) if step == 0 else campaign.steps[step-1]
    subject, missing_subject = render(content['subject'], recipient.variables)
    body, missing_body = render(content['body'], recipient.variables)
    if missing_subject or missing_body:
        raise HTTPException(422, 'Unresolved personalization prevents scheduling')
    # Reply-based opt-out works without exposing a public endpoint or bearer token.
    body += '\n\nTo stop further outreach, reply with "unsubscribe".'
    message = OutboundEmail(recipient_id=recipient.id, step=step, subject=subject, body=body,
                            message_id=make_msgid(domain=campaign.sender_email.split('@')[-1]), due_at=due_at)
    db.add(message)
    return message


def stop_recipient(db, recipient, outcome):
    recipient.outcome, recipient.stopped, recipient.outreach_active = outcome, True, False
    db.execute(update(OutboundEmail).where(OutboundEmail.recipient_id == recipient.id,
               OutboundEmail.status == 'queued').values(status='cancelled'))


def suppress_address(db, email, reason, actor=None):
    if not suppressed(db, email):
        db.add(EmailSuppression(email=email, reason=reason, actor_id=actor.id if actor else None))
    for recipient in db.scalars(select(CampaignRecipient).where(CampaignRecipient.email == email)):
        stop_recipient(db, recipient, 'do_not_contact')


def finish_campaign(db, campaign):
    db.flush()
    ids = select(CampaignRecipient.id).where(CampaignRecipient.campaign_id == campaign.id)
    pending = db.scalar(select(OutboundEmail.id).where(OutboundEmail.recipient_id.in_(ids),
                         OutboundEmail.status.in_(['queued', 'sending'])).limit(1))
    if not pending and campaign.status == 'active':
        failures = db.scalar(select(OutboundEmail.id).where(OutboundEmail.recipient_id.in_(ids),
                              OutboundEmail.status.in_(['failed', 'uncertain'])).limit(1))
        campaign.status = 'failed' if failures else 'completed'
        for recipient in recipients(db, campaign):
            recipient.outreach_active = False
