from typing import Annotated, Literal
from uuid import UUID
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, delete, func, text

from app.api.dependencies import DB, require
from app.api.organizations import get_organization, scoped
from app.core.permissions import effective_permissions
from app.core.security import audit
from app.models import (EmailTemplate, EmailCampaign, CampaignRecipient, CampaignApproval, OutboundEmail,
                        InboundEmail, EmailSuppression, MailboxSyncState, CampaignWorkerState, Contact, Organization, User, utcnow)
from app.services.campaign_runtime import wake_worker
from app.services.campaigns import (VARIABLES, Content, TemplateInput, CampaignInput, render, variables_for,
    recipients, validate_campaign, sender_configuration, queue_message, stop_recipient, suppress_address)

router = APIRouter(prefix='/campaigns', tags=['Campaigns'])
Actor = Annotated[User, Depends(require('campaigns.read'))]


def manager(actor):
    return any(r.name in ('CEO', 'Manager') for r in actor.roles)


def lock(db):
    # Shared with workers: changes to approval, suppression and eligibility cannot race a send.
    db.execute(text('SELECT pg_advisory_xact_lock(98171623)'))


def get_campaign(db, actor, id, write=False):
    row = db.get(EmailCampaign, id)
    if not row:
        raise HTTPException(404, 'Campaign not found')
    if write and not manager(actor) and row.owner_id != actor.id:
        raise HTTPException(403, 'You can view this campaign, but only its owner or a manager can change it')
    return row


def record(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


def summary(db, row):
    result = record(row)
    ids = select(CampaignRecipient.id).where(CampaignRecipient.campaign_id == row.id)
    result.update(owner=db.get(User, row.owner_id).full_name,
        recipient_count=db.scalar(select(func.count()).select_from(CampaignRecipient).where(CampaignRecipient.campaign_id == row.id)),
        sent=db.scalar(select(func.count()).select_from(OutboundEmail).where(OutboundEmail.recipient_id.in_(ids), OutboundEmail.status == 'accepted')),
        replies=db.scalar(select(func.count()).select_from(InboundEmail).where(InboundEmail.recipient_id.in_(ids))),
        queued=db.scalar(select(func.count()).select_from(OutboundEmail).where(OutboundEmail.recipient_id.in_(ids), OutboundEmail.status == 'queued')),
        failed=db.scalar(select(func.count()).select_from(OutboundEmail).where(OutboundEmail.recipient_id.in_(ids), OutboundEmail.status.in_(['failed', 'uncertain']))),
        pending_followups=db.scalar(select(func.count()).select_from(OutboundEmail).where(OutboundEmail.recipient_id.in_(ids), OutboundEmail.step > 0, OutboundEmail.status == 'queued')))
    return result


@router.get('/templates')
def templates(db: DB, actor: Actor):
    return [record(t) for t in db.scalars(select(EmailTemplate).order_by(EmailTemplate.updated_at.desc()))]


@router.post('/templates', status_code=201)
def create_template(data: TemplateInput, db: DB, actor: Actor):
    row = EmailTemplate(**data.model_dump(), creator_id=actor.id)
    db.add(row); db.flush()
    audit(db, actor, 'template.created', 'email_template', row.id)
    db.commit()
    return record(row)


@router.put('/templates/{id}')
def edit_template(id: UUID, data: TemplateInput, db: DB, actor: Actor):
    row = db.get(EmailTemplate, id)
    if not row or (not manager(actor) and row.creator_id != actor.id):
        raise HTTPException(404, 'Template not found')
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    audit(db, actor, 'template.updated', 'email_template', row.id)
    db.commit()
    return record(row)


@router.get('/contacts')
def contacts(db: DB, actor: Actor, q: str = Query(default='', max_length=180)):
    orgs = db.scalars(scoped(select(Organization).where(Organization.name.icontains(q, autoescape=True)), actor).order_by(Organization.name).limit(50))
    return [dict(id=o.id, name=o.name, contacts=[dict(id=c.id, full_name=c.full_name, job_title=c.job_title,
        email=c.email, recommended=c.is_primary or any(word in (c.job_title or '').lower() for word in ('director', 'manager', 'partnership', 'procurement', 'ceo')))
        for c in o.contacts if c.email]) for o in orgs]


class PreviewInput(Content):
    contact_id: UUID


@router.post('/preview')
def preview(data: PreviewInput, db: DB, actor: Actor):
    contact = db.get(Contact, data.contact_id)
    if not contact:
        raise HTTPException(404, 'Contact not found')
    get_organization(db, actor, contact.organization_id)
    variables = variables_for(contact, actor)
    subject, sm = render(data.subject, variables)
    body, bm = render(data.body, variables)
    return dict(subject=subject, body=body, missing=sorted(set(sm + bm)), variables=VARIABLES)


@router.get('/suppressions')
def suppressions(db: DB, actor: Actor):
    if not manager(actor):
        raise HTTPException(403, 'Manager permission required')
    return [record(r) for r in db.scalars(select(EmailSuppression).order_by(EmailSuppression.created_at.desc()))]


class SuppressionInput(BaseModel):
    email: EmailStr
    reason: str = Field(min_length=1, max_length=300)


@router.post('/suppressions')
def add_suppression(data: SuppressionInput, db: DB, actor: Actor):
    if not manager(actor):
        raise HTTPException(403, 'Manager permission required')
    lock(db)
    suppress_address(db, str(data.email).lower(), data.reason, actor)
    audit(db, actor, 'email.suppressed', 'email_suppression')
    db.commit()
    return {'message': 'Address suppressed; pending outreach stopped'}


@router.get('')
def list_campaigns(db: DB, actor: Actor, q: str = Query(default='', max_length=150)):
    query = select(EmailCampaign)
    all_rows = [summary(db, r) for r in db.scalars(query.order_by(EmailCampaign.created_at.desc()))]
    sync = db.get(MailboxSyncState, 1)
    return dict(items=[r for r in all_rows if q.lower() in r['name'].lower()],
        metrics=dict(active=sum(r['status'] == 'active' for r in all_rows), sent=sum(r['sent'] for r in all_rows),
                     replies=sum(r['replies'] for r in all_rows), pending=sum(r['pending_followups'] for r in all_rows)),
        mailbox=dict(last_success=sync.last_success, error=sync.error) if sync else None)


@router.get('/runtime')
def runtime(db: DB, actor: Actor):
    state = db.get(CampaignWorkerState, 1)
    sync = db.get(MailboxSyncState, 1)
    return dict(running=bool(state and utcnow() - state.last_heartbeat < timedelta(minutes=2)),
        phase=state.phase if state else 'offline', last_heartbeat=state.last_heartbeat if state else None,
        last_completed=state.last_completed if state else None, error=state.error if state else None,
        mailbox_last_success=sync.last_success if sync else None, mailbox_error=sync.error if sync else None)


def apply_campaign(db, actor, row, data):
    if len(set(data.contact_ids)) != len(data.contact_ids):
        raise HTTPException(422, 'Duplicate contacts are not allowed')
    selected = []
    for id in data.contact_ids:
        contact = db.get(Contact, id)
        if not contact or not contact.email:
            raise HTTPException(422, 'Select contacts with email addresses')
        get_organization(db, actor, contact.organization_id)
        selected.append(contact)
    if len({c.email.lower() for c in selected}) != len(selected):
        raise HTTPException(422, 'Choose only one contact per email address')
    for key, value in data.model_dump(exclude={'contact_ids', 'version'}).items():
        setattr(row, key, value)
    row.status, row.approved_version = 'draft', None
    db.flush()
    db.execute(delete(CampaignRecipient).where(CampaignRecipient.campaign_id == row.id))
    owner = db.get(User, row.owner_id)
    for contact in selected:
        db.add(CampaignRecipient(campaign_id=row.id, contact_id=contact.id, organization_id=contact.organization_id,
             email=contact.email.lower(), variables=variables_for(contact, owner)))
    audit(db, actor, 'campaign.saved', 'email_campaign', row.id)


@router.post('', status_code=201)
def create_campaign(data: CampaignInput, db: DB, actor: Actor):
    row = EmailCampaign(owner_id=actor.id, name=data.name, objective=data.objective, subject=data.subject, body=data.body)
    db.add(row)
    apply_campaign(db, actor, row, data)
    db.commit()
    return summary(db, row)


@router.put('/{id}')
def edit_campaign(id: UUID, data: CampaignInput, db: DB, actor: Actor):
    lock(db)
    row = get_campaign(db, actor, id, write=True)
    if row.status not in ('draft', 'rejected', 'approved', 'pending_approval'):
        raise HTTPException(409, 'Only unlaunched campaigns can be edited')
    if not manager(actor) and row.status not in ('draft', 'rejected'):
        raise HTTPException(403, 'Staff can edit their own drafts only')
    if data.version != row.version:
        raise HTTPException(409, 'Campaign changed. Reload before saving')
    row.version += 1
    apply_campaign(db, actor, row, data)
    db.commit()
    return summary(db, row)


@router.get('/{id}')
def detail(id: UUID, db: DB, actor: Actor):
    row = get_campaign(db, actor, id)
    result = summary(db, row)
    result['recipients'] = [dict(**record(r), organization=db.get(Organization, r.organization_id).name,
        outgoing=[record(m) for m in db.scalars(select(OutboundEmail).where(OutboundEmail.recipient_id == r.id).order_by(OutboundEmail.step))],
        incoming=[record(m) for m in db.scalars(select(InboundEmail).where(InboundEmail.recipient_id == r.id).order_by(InboundEmail.created_at))]) for r in recipients(db, row)]
    result['approvals'] = [record(a) for a in db.scalars(select(CampaignApproval).where(CampaignApproval.campaign_id == id).order_by(CampaignApproval.created_at))]
    return result


class ActionInput(BaseModel):
    action: Literal['review', 'submit', 'approve', 'reject', 'launch', 'pause', 'resume', 'cancel']
    version: int
    note: str = Field(default='', max_length=2000)


@router.post('/{id}/actions')
def action(id: UUID, data: ActionInput, db: DB, actor: Actor):
    lock(db)
    row = get_campaign(db, actor, id, write=data.action != 'review')
    if row.version != data.version:
        raise HTTPException(409, 'Campaign changed. Reload before continuing')
    operation = data.action
    if operation not in ('review', 'submit') and not manager(actor):
        if operation != 'launch' or 'campaigns.launch' not in effective_permissions(actor):
            raise HTTPException(403, 'Manager permission required')
    transitions = dict(submit=(['draft', 'rejected'], 'pending_approval'), approve=(['pending_approval'], 'approved'),
        reject=(['pending_approval'], 'rejected'), launch=(['approved'], 'active'), pause=(['active'], 'paused'),
        resume=(['paused'], 'active'), cancel=(['draft', 'pending_approval', 'approved', 'active', 'paused', 'rejected', 'failed'], 'cancelled'))
    if operation == 'review':
        validate_campaign(db, row)
        return {'message': 'All recipients and sequence messages passed validation'}
    allowed, target = transitions[operation]
    if row.status not in allowed:
        raise HTTPException(409, 'This action is not available in the current campaign state')
    if operation in ('submit', 'approve', 'launch'):
        validate_campaign(db, row)
    if operation in ('approve', 'reject'):
        row.approved_version = row.version if operation == 'approve' else None
        db.add(CampaignApproval(campaign_id=row.id, actor_id=actor.id, version=row.version, decision=operation, note=data.note))
    if operation in ('launch', 'resume'):
        config = sender_configuration(db)
        if row.approved_version != row.version:
            raise HTTPException(409, 'Campaign requires a new approval')
        if operation == 'resume' and (row.sender_email != config.sender_email or row.sender_name != config.sender_name):
            raise HTTPException(409, 'Sender identity changed. Cancel and create a new campaign for approval.')
        if row.steps and (not config.imap_host or not config.imap_password_encrypted):
            raise HTTPException(409, 'Configure incoming mail before enabling automatic follow-ups')
        if operation == 'launch':
            row.sender_email, row.sender_name = config.sender_email, config.sender_name
            for recipient in recipients(db, row):
                conflict = db.scalar(select(CampaignRecipient.id).where(CampaignRecipient.email == recipient.email, CampaignRecipient.outreach_active.is_(True)))
                if conflict:
                    raise HTTPException(409, 'A selected address already has active outreach')
                recipient.outreach_active = True
                queue_message(db, row, recipient, 0, utcnow())
    if operation == 'cancel':
        for recipient in recipients(db, row):
            stop_recipient(db, recipient, 'cancelled')
    row.status, row.issue = target, None
    audit(db, actor, 'campaign.' + operation, 'email_campaign', row.id)
    db.commit()
    if operation in ('launch', 'resume'):
        wake_worker()
    return summary(db, row)


class OutcomeInput(BaseModel):
    outcome: Literal['replied', 'interested', 'not_interested', 'do_not_follow_up', 'requires_attention', 'do_not_contact']


@router.post('/{id}/recipients/{recipient_id}/outcome')
def outcome(id: UUID, recipient_id: UUID, data: OutcomeInput, db: DB, actor: Actor):
    lock(db)
    get_campaign(db, actor, id, write=True)
    row = db.get(CampaignRecipient, recipient_id)
    if not row or row.campaign_id != id:
        raise HTTPException(404, 'Recipient not found')
    if data.outcome == 'do_not_contact':
        suppress_address(db, row.email, 'Manual do not contact', actor)
    else:
        stop_recipient(db, row, data.outcome)
    audit(db, actor, 'campaign.recipient_outcome', 'contact', row.contact_id, row.organization_id, outcome=data.outcome)
    db.commit()
    return {'message': 'Outcome saved and pending follow-ups stopped'}
