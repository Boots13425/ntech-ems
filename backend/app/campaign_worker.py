"""Persistent campaign worker, started by the API (or optionally as a separate service).

A dedicated PostgreSQL session lock serializes workers and campaign mutations, including
the SMTP boundary. A crash after claiming a message leaves it uncertain, never retried.
"""
import hashlib
import imaplib
import re
import smtplib
import ssl
import time
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from sqlalchemy import select, text, func
from sqlalchemy.orm import Session

from app.db.session import engine
from app.core.security import audit
from app.services.notifications import notify
from app.models import (EmailConfiguration, EmailCampaign, CampaignRecipient, OutboundEmail, InboundEmail,
                        MailboxSyncState, CampaignWorkerState, Contact, AuditEvent, utcnow)
from app.services.email_configuration import decrypt
from app.services.campaigns import (suppressed, stop_recipient, suppress_address, queue_message, finish_campaign, valid_address)


def mailbox_identity(config):
    # Versioned to replay the campaign window after the old full-inbox scanner.
    return hashlib.sha256(f'campaign-window-v2:{config.imap_host}:{config.imap_port}:{decrypt(config.imap_username_encrypted)}:{config.sender_email}'.encode()).hexdigest()


def match_reply(db, message, sender_email=None):
    inbound_id = str(message.get('Message-ID', ''))[:998]
    # Gmail All Mail contains sent messages too. Never count our own outbound jobs as replies.
    if inbound_id and db.scalar(select(OutboundEmail.id).where(OutboundEmail.message_id == inbound_id)):
        return None
    refs = re.findall(r'<[^<>\s]+>', str(message.get('In-Reply-To', '')) + ' ' + str(message.get('References', '')))
    sender = parseaddr(str(message.get('From', '')))[1].lower()[:254]
    outgoing = db.scalar(select(OutboundEmail).where(OutboundEmail.message_id.in_(refs)).order_by(OutboundEmail.created_at.desc())) if refs else None
    recipient = db.get(CampaignRecipient, outgoing.recipient_id) if outgoing else None
    if not recipient:
        # Unthreaded messages from known recipients need human review; still hold automation.
        recipient = db.scalar(select(CampaignRecipient).join(OutboundEmail).where(CampaignRecipient.email == sender,
            OutboundEmail.status.in_(['accepted', 'uncertain'])).order_by(OutboundEmail.created_at.desc()))
    if not recipient:
        return None
    if sender_email and sender == sender_email.lower() and recipient.email != sender:
        return None
    if inbound_id and db.scalar(select(InboundEmail.id).where(InboundEmail.recipient_id == recipient.id, InboundEmail.message_id == inbound_id)):
        return None
    automatic = str(message.get('Auto-Submitted', 'no')).lower() != 'no'
    outcome = 'replied' if outgoing and sender == recipient.email and not automatic else 'requires_attention'
    return recipient, sender, inbound_id, outcome


def ingest(db, raw, key, sender_email=None):
    if db.scalar(select(InboundEmail.id).where(InboundEmail.mailbox_key == key)):
        return
    message = BytesParser(policy=policy.default).parsebytes(raw)
    matched = match_reply(db, message, sender_email)
    if not matched:
        return
    recipient, sender, inbound_id, outcome = matched
    body = ''
    for part in message.walk():
        if part.get_content_type() == 'text/plain' and part.get_content_disposition() != 'attachment':
            payload = part.get_payload(decode=True) or b''
            try:
                body = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')[:50000]
            except LookupError:
                body = payload.decode('utf-8', errors='replace')[:50000]
            break
    if not body:
        body = '[No plain-text content available. Review this message in the company mailbox.]'
    db.add(InboundEmail(recipient_id=recipient.id, mailbox_key=key, message_id=inbound_id,
                        subject=str(message.get('Subject', ''))[:2000], body=body, sender=sender))
    # All matched responses stop automation, including bounces, auto-replies and ambiguous senders.
    stop_recipient(db, recipient, outcome)
    # Only inspect the new text, not quoted outbound content containing the opt-out footer.
    new_text = re.split(r'(?im)^\s*(?:>|on .+wrote:|from:|--\s*$)', body)[0].strip()
    if sender == recipient.email and re.search(r'(?i)\b(unsubscribe|remove me|do not contact|stop emailing|stop contacting)\b', str(message.get('Subject', '')) + '\n' + new_text):
        suppress_address(db, recipient.email, 'Opt-out received by email')
    campaign = db.get(EmailCampaign, recipient.campaign_id)
    notify(db, campaign.owner_id, 'campaign.reply', 'New campaign response',
           f'A response was received for "{campaign.name}". Open the campaign to review it.',
           path=f'/campaigns/{campaign.id}', permission='campaigns.read')
    audit(db, None, 'campaign.reply_received', 'contact', recipient.contact_id, recipient.organization_id)


def reply_folder(mailbox, config):
    """Discover Gmail's localized All Mail folder using the standard special-use flag."""
    gmail = config.imap_host.lower() in ('imap.gmail.com', 'imap.googlemail.com') or b'X-GM-EXT-1' in mailbox.capabilities
    if gmail:
        status, folders = mailbox.list()
        if status != 'OK':
            raise ValueError('Cannot discover Gmail mailboxes')
        for folder in folders:
            if not isinstance(folder, bytes):
                continue
            matched = re.match(rb'^\(([^)]*)\)\s+(?:"(?:[^"\\]|\\.)*"|NIL)\s+(.+)$', folder)
            if matched and b'\\All' in matched.group(1).split():
                return matched.group(2)  # Preserve quoting and IMAP UTF-7 from LIST.
        raise ValueError('Gmail All Mail must be available over IMAP')
    return b'INBOX'


def sync_mailbox(db, config):
    state = db.get(MailboxSyncState, 1)
    if not state:
        state = MailboxSyncState(id=1)
        db.add(state); db.commit()
    if not config or not config.imap_host or not config.imap_password_encrypted:
        state.error = 'Incoming mailbox is not configured; automatic follow-ups are held.'
        db.commit()
        return
    mailbox = None
    try:
        mailbox = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, ssl_context=ssl.create_default_context(), timeout=15)
        mailbox.login(decrypt(config.imap_username_encrypted), decrypt(config.imap_password_encrypted))
        folder = reply_folder(mailbox, config)
        status, _ = mailbox.select(folder, readonly=True)
        if status != 'OK':
            raise ValueError('Mailbox unavailable')
        validity = hashlib.sha256(folder).hexdigest()[:12] + ':' + (mailbox.response('UIDVALIDITY')[1] or [b''])[0].decode()
        identity = mailbox_identity(config)
        if state.identity != identity or state.uid_validity != validity:
            state.identity, state.uid_validity, state.last_uid, state.last_success = identity, validity, 0, None
        first_sent = db.scalar(select(func.min(func.coalesce(OutboundEmail.accepted_at, OutboundEmail.created_at))).where(
            OutboundEmail.status.in_(['accepted', 'uncertain', 'sending'])))
        if not first_sent:
            state.error, state.last_success = None, utcnow()
            db.commit()
            return
        # Messages older than the first actual campaign send cannot be campaign replies.
        # Include a day of overlap for IMAP server timezone/internal-date differences.
        start = first_sent - timedelta(days=1)
        month = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')[start.month - 1]
        since = f'{start.day:02d}-{month}-{start.year}'
        status, found = mailbox.uid('search', None, 'SINCE', since, 'UID', f'{state.last_uid + 1}:*')
        if status != 'OK':
            raise ValueError('Mailbox search failed')
        uids = sorted(int(u) for u in (found[0] or b'').split() if int(u) > state.last_uid)
        deadline = time.monotonic() + 20
        batch = uids[:200]
        headers = {}
        if batch:
            # Fetch headers in one request, not hundreds of message bodies from unrelated mail.
            status, parts = mailbox.uid('fetch', ','.join(str(uid) for uid in batch), '(UID BODY.PEEK[HEADER])')
            if status != 'OK':
                raise ValueError('Mailbox header fetch failed')
            for part in parts:
                if isinstance(part, tuple) and isinstance(part[1], bytes):
                    match = re.search(rb'\bUID\s+(\d+)\b', part[0])
                    if match:
                        headers[int(match.group(1))] = part[1]
        for uid in batch:
            if time.monotonic() >= deadline:
                break
            header = headers.get(uid)
            if header is None:
                raise ValueError('Mailbox header unavailable; do not advance the cursor')
            parsed = BytesParser(policy=policy.default).parsebytes(header)
            if match_reply(db, parsed, config.sender_email):
                status, parts = mailbox.uid('fetch', str(uid), '(BODY.PEEK[TEXT]<0.65536>)')
                if status != 'OK':
                    raise ValueError('Mailbox reply fetch failed')
                chunks = [part[1] for part in parts if isinstance(part, tuple) and isinstance(part[1], bytes)]
                if not chunks:
                    raise ValueError('Mailbox reply unavailable; do not advance the cursor')
                ingest(db, header + b''.join(chunks), hashlib.sha256(f'{identity}:{validity}:{uid}'.encode()).hexdigest(), config.sender_email)
            state.last_uid = uid
            worker = db.get(CampaignWorkerState, 1)
            if worker:
                worker.last_heartbeat = utcnow()
            db.commit()
        state.error = 'Mailbox catch-up in progress; follow-ups are held.' if uids and state.last_uid < uids[-1] else None
        if not state.error:
            state.last_success = utcnow()
        db.commit()
    except Exception:
        db.rollback()
        state = db.get(MailboxSyncState, 1)
        if state:
            state.error = 'Mailbox synchronization failed. Check incoming settings and provider access.'
            db.commit()
    finally:
        if mailbox:
            try:
                mailbox.logout()
            except Exception:
                pass


def deliver(config, job, recipient, parent):
    """Return accepted/failed/uncertain; only a failed pre-DATA attempt may be retried."""
    smtp, submitting = None, False
    try:
        context = ssl.create_default_context()
        if config.security == 'tls':
            smtp = smtplib.SMTP_SSL(config.host, config.port, timeout=20, context=context)
        elif config.security == 'starttls':
            smtp = smtplib.SMTP(config.host, config.port, timeout=20)
            smtp.ehlo(); smtp.starttls(context=context); smtp.ehlo()
        else:
            return 'failed', 'Authenticated TLS SMTP is required', False
        smtp.login(decrypt(config.username_encrypted), decrypt(config.password_encrypted))
        message = EmailMessage()
        message['From'] = formataddr((config.sender_name, config.sender_email))
        message['To'], message['Subject'], message['Message-ID'] = recipient.email, job.subject, job.message_id
        from email.utils import format_datetime
        message['Date'] = format_datetime(utcnow())
        message['Reply-To'] = config.sender_email
        message['List-Unsubscribe'] = f'<mailto:{config.sender_email}?subject=unsubscribe>'
        if parent:
            message['In-Reply-To'] = parent.message_id
            message['References'] = parent.message_id
        message.set_content(job.body)
        submitting = True
        rejected = smtp.send_message(message, from_addr=config.sender_email, to_addrs=[recipient.email])
        if rejected:
            return 'failed', 'SMTP rejected the recipient', False
        return 'accepted', None, False
    except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
        return 'failed', 'SMTP explicitly rejected the message', False
    except Exception:
        return ('uncertain', 'SMTP outcome unknown; inspect the mailbox before further outreach', False) if submitting else ('failed', 'Connection or authentication failed before submission', True)
    finally:
        if smtp:
            smtp.close()


def process_one(db, config, transport=None, initial_only=False):
    transport = transport or deliver
    # Owning the worker lock means any leftover sending claim belongs to a crashed worker.
    for old in db.scalars(select(OutboundEmail).where(OutboundEmail.status == 'sending')):
        old.status, old.error = 'uncertain', 'Worker interrupted after claim; delivery may have occurred'
        stop_recipient(db, db.get(CampaignRecipient, old.recipient_id), 'requires_attention')
    db.commit()
    if not config:
        return
    query = select(OutboundEmail).join(CampaignRecipient).join(EmailCampaign).where(
        OutboundEmail.status == 'queued', OutboundEmail.due_at <= utcnow(), EmailCampaign.status == 'active')
    if initial_only:
        query = query.where(OutboundEmail.step == 0)
    jobs = db.scalars(query.order_by(OutboundEmail.due_at).limit(100)).all()
    for job in jobs:
        recipient = db.get(CampaignRecipient, job.recipient_id)
        campaign = db.get(EmailCampaign, recipient.campaign_id)
        contact = db.get(Contact, recipient.contact_id) if recipient.contact_id else None
        if recipient.stopped or not valid_address(recipient.email) or suppressed(db, recipient.email) or not contact or contact.organization.is_archived or contact.email != recipient.email:
            stop_recipient(db, recipient, 'do_not_follow_up'); db.commit(); continue
        if campaign.approved_version != campaign.version or config.sender_email != campaign.sender_email or config.sender_name != campaign.sender_name:
            campaign.status, campaign.issue = 'paused', 'Sender identity or approval changed. Review before further sending.'
            db.commit(); continue
        if not config.username_encrypted or not config.password_encrypted or config.security == 'none':
            campaign.status, campaign.issue = 'paused', 'Authenticated TLS SMTP configuration required'
            db.commit(); continue
        if job.step > 0:
            state = db.get(MailboxSyncState, 1)
            if not state or state.error or not state.last_success or state.identity != mailbox_identity(config) or utcnow() - state.last_success > timedelta(minutes=5):
                continue
        recent = db.scalar(select(func.count()).select_from(AuditEvent).where(
            AuditEvent.action == 'campaign.email_attempt', AuditEvent.created_at >= utcnow() - timedelta(hours=1)))
        if recent >= config.hourly_limit:
            break
        parent = db.scalar(select(OutboundEmail).where(OutboundEmail.recipient_id == recipient.id, OutboundEmail.step == job.step-1)) if job.step else None
        job.status, job.attempts = 'sending', job.attempts + 1
        audit(db, None, 'campaign.email_attempt', 'contact', recipient.contact_id, recipient.organization_id,
              outbound_id=str(job.id), attempt=job.attempts)
        db.commit()  # Durable claim before any SMTP operation.
        status, error, retryable = transport(config, job, recipient, parent)
        job.status, job.error = status, error
        if status == 'accepted':
            job.accepted_at = utcnow()
            if job.step < len(campaign.steps):
                queue_message(db, campaign, recipient, job.step+1, job.accepted_at + timedelta(days=campaign.steps[job.step]['days']))
            else:
                recipient.outreach_active = False
        elif retryable and job.attempts < 3:
            job.status, job.due_at = 'queued', utcnow() + timedelta(minutes=5 * job.attempts)
        else:
            stop_recipient(db, recipient, 'requires_attention')
        audit(db, None, 'campaign.email_' + status, 'contact', recipient.contact_id, recipient.organization_id,
              outbound_id=str(job.id), attempt=job.attempts)
        db.commit()
        break
    for campaign in db.scalars(select(EmailCampaign).where(EmailCampaign.status == 'active')):
        finish_campaign(db, campaign)
    db.commit()


def tick():
    # Session-level locks survive the commit before SMTP. A dedicated connection is
    # closed after unlock, so locks can never leak into the general connection pool.
    with engine.connect() as connection:
        acquired = connection.scalar(text('SELECT pg_try_advisory_lock(98171623)'))
        connection.commit()
        if not acquired:
            return
        settings_acquired = False
        try:
            settings_acquired = connection.scalar(text('SELECT pg_try_advisory_lock(98171622)'))
            connection.commit()
            if not settings_acquired:
                return
            with Session(bind=connection, expire_on_commit=False) as db:
                state = db.get(CampaignWorkerState, 1)
                if not state:
                    state = CampaignWorkerState(id=1)
                    db.add(state)
                state.last_heartbeat, state.phase, state.error = utcnow(), 'sending', None
                db.commit()
                try:
                    config = db.get(EmailConfiguration, 1)
                    # Initial outreach should not wait for a large historical inbox scan.
                    process_one(db, config, initial_only=True)
                    state.phase, state.last_heartbeat = 'syncing', utcnow()
                    db.commit()
                    sync_mailbox(db, config)
                    state.phase, state.last_heartbeat = 'sending', utcnow()
                    db.commit()
                    process_one(db, config)
                    state.phase, state.last_heartbeat, state.last_completed = 'idle', utcnow(), utcnow()
                    db.commit()
                except Exception:
                    db.rollback()
                    state = db.get(CampaignWorkerState, 1)
                    state.phase, state.last_heartbeat = 'error', utcnow()
                    state.error = 'Campaign processing failed; the server will retry. Check the server log.'
                    db.commit()
                    raise
        finally:
            connection.rollback()
            if settings_acquired:
                connection.execute(text('SELECT pg_advisory_unlock(98171622)'))
            connection.execute(text('SELECT pg_advisory_unlock(98171623)'))
            connection.commit()


def main():
    import logging
    while True:
        try:
            tick()
        except Exception as exc:
            logging.getLogger('ntech').error('campaign_worker_failure type=%s', type(exc).__name__)
        time.sleep(15)


if __name__ == '__main__':
    main()
