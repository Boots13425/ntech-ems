from datetime import timedelta
from email.message import EmailMessage
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import IntegrityError

from conftest import authenticate, post
from app.db.session import SessionLocal, engine
from app.models import (EmailCampaign, CampaignRecipient, EmailConfiguration, OutboundEmail, InboundEmail,
    MailboxSyncState, EmailSuppression, Contact, Organization, User, AuditEvent, utcnow)
from app.services.email_configuration import encrypt
from app.services.campaigns import render
from app.campaign_worker import process_one, ingest, mailbox_identity, sync_mailbox, deliver


def setup(client, role='CEO', steps=True, body='Hello {{contact_name}} at {{company_name}}'):
    owner, *_ = authenticate(client, role=role, responsibilities=['Sales and Outreach'])
    org = post(client, '/organizations', dict(name='Campaign Test Organization', country='Cameroon', classifications=['prospect'])).json()
    contact = post(client, f"/organizations/{org['id']}/contacts", dict(full_name='Test Contact', job_title='Director', email='contact@example.org', is_primary=True)).json()
    with SessionLocal() as db:
        db.add(EmailConfiguration(id=1, host='smtp.example.org', port=465, security='tls', sender_name='Company', sender_email='sender@example.org',
            username_encrypted=encrypt('sender@example.org'), password_encrypted=encrypt('secret'), imap_host='imap.example.org', imap_port=993,
            imap_username_encrypted=encrypt('sender@example.org'), imap_password_encrypted=encrypt('secret'), hourly_limit=50))
        db.commit()
    payload = dict(name='Partnership launch', objective='Partnership', description='Test only', subject='Hello {{company_name}}', body=body,
        contact_ids=[contact['id']], steps=[dict(days=4, subject='Following up', body='Hello {{contact_name}}')] if steps else [])
    result = post(client, '/campaigns', payload)
    assert result.status_code == 201, result.text
    return result.json(), payload, contact, org


def act(client, campaign, action):
    return post(client, f"/campaigns/{campaign['id']}/actions", dict(action=action, version=campaign['version']))


def launch(client, campaign):
    for action in ['submit', 'approve', 'launch']:
        result = act(client, campaign, action)
        assert result.status_code == 200, result.text


def work(transport=None):
    transport = transport or MagicMock(return_value=('accepted', None, False))
    with SessionLocal() as db:
        process_one(db, db.get(EmailConfiguration, 1), transport)
    return transport


def due_and_healthy():
    with SessionLocal() as db:
        job = db.scalar(select(OutboundEmail).where(OutboundEmail.step == 1))
        job.due_at = utcnow() - timedelta(seconds=1)
        db.add(MailboxSyncState(id=1, identity=mailbox_identity(db.get(EmailConfiguration, 1)), last_success=utcnow()))
        db.commit()


def test_template_contacts_preview_and_snapshot(client):
    c, payload, contact, org = setup(client)
    t = post(client, '/campaigns/templates', dict(name='Reusable', category='Partnership', subject=payload['subject'], body=payload['body']))
    assert t.status_code == 201
    assert client.get('/api/campaigns/templates').json()[0]['name'] == 'Reusable'
    selected = client.get('/api/campaigns/contacts?q=Campaign').json()
    assert selected[0]['contacts'][0]['recommended'] is True
    preview = post(client, '/campaigns/preview', dict(subject=payload['subject'], body=payload['body'], contact_id=contact['id'])).json()
    assert preview['body'] == 'Hello Test Contact at Campaign Test Organization'
    assert preview['missing'] == []
    launch(client, c)
    with SessionLocal() as db:
        job = db.scalar(select(OutboundEmail))
        assert job.status == 'queued' and 'Test Contact' in job.body
        assert '{{' not in job.subject and job.message_id.startswith('<')
    assert act(client, c, 'launch').status_code == 409


def test_missing_variables_and_staff_rbac(client):
    c, payload, contact, _ = setup(client, role='Staff', body='Hello {{unknown}}')
    assert act(client, c, 'submit').status_code == 422
    payload['body'] = 'Hello {{contact_name}}'; payload['version'] = c['version']
    response = post(client, f"/campaigns/{c['id']}", payload, method='put')
    assert response.status_code == 200, response.text
    c = response.json()
    assert act(client, c, 'submit').status_code == 200
    assert act(client, c, 'approve').status_code == 403
    assert act(client, c, 'launch').status_code == 403
    assert client.get('/api/campaigns/suppressions').status_code == 403
    assert post(client, '/campaigns/preview', dict(subject='Subject', body='{{contact_position}}', contact_id=contact['id'])).status_code == 200


def test_approval_invalidated_and_stale_edit_rejected(client):
    c, payload, *_ = setup(client)
    act(client, c, 'submit'); act(client, c, 'approve')
    payload.update(version=c['version'], body='New approved content required')
    response = post(client, f"/campaigns/{c['id']}", payload, method='put')
    assert response.status_code == 200
    changed = response.json()
    assert changed['status'] == 'draft' and changed['approved_version'] is None
    assert post(client, f"/campaigns/{c['id']}", payload, method='put').status_code == 409
    assert act(client, changed, 'launch').status_code == 409


def test_delivery_followup_and_reply_idempotence(client):
    c, *_ = setup(client)
    launch(client, c)
    transport = work()
    transport.assert_called_once()
    with SessionLocal() as db:
        first, followup = db.scalars(select(OutboundEmail).order_by(OutboundEmail.step)).all()
        assert first.status == 'accepted' and followup.status == 'queued'
        assert followup.due_at - first.accepted_at == timedelta(days=4)
        msg = EmailMessage()
        msg['From'], msg['To'], msg['Message-ID'], msg['In-Reply-To'] = 'contact@example.org', 'sender@example.org', '<reply@example.org>', first.message_id
        msg['Subject'] = 'Interested'; msg.set_content('Please call us')
        ingest(db, msg.as_bytes(), 'mailbox-1'); db.commit()
        ingest(db, msg.as_bytes(), 'mailbox-1'); ingest(db, msg.as_bytes(), 'mailbox-new-uid'); db.commit()
        assert db.scalar(select(func.count()).select_from(InboundEmail)) == 1
        assert db.get(OutboundEmail, followup.id).status == 'cancelled'
        assert db.scalar(select(CampaignRecipient)).stopped
    assert not work().called
    stats = client.get('/api/campaigns').json()['metrics']
    assert stats == dict(active=0, sent=1, replies=1, pending=0)


def test_followup_held_until_sync_healthy(client):
    c, *_ = setup(client)
    launch(client, c); work(); due_and_healthy()
    with SessionLocal() as db:
        db.get(MailboxSyncState, 1).error = 'Offline'; db.commit()
    assert not work().called
    with SessionLocal() as db:
        db.get(MailboxSyncState, 1).error = None; db.commit()
    assert work().called
    assert client.get(f"/api/campaigns/{c['id']}").json()['status'] == 'completed'


@pytest.mark.parametrize('action', ['pause', 'cancel'])
def test_paused_cancelled_never_send(client, action):
    c, *_ = setup(client)
    launch(client, c)
    assert act(client, c, action).status_code == 200
    assert not work().called
    if action == 'pause':
        assert act(client, c, 'resume').status_code == 200
        assert work().called


def test_suppression_and_conflicting_outreach(client):
    c, payload, *_ = setup(client)
    launch(client, c)
    other = post(client, '/campaigns', payload).json()
    act(client, other, 'submit'); act(client, other, 'approve')
    assert act(client, other, 'launch').status_code == 409
    result = post(client, '/campaigns/suppressions', dict(email='contact@example.org', reason='Requested opt-out'))
    assert result.status_code == 200
    assert not work().called
    assert act(client, other, 'launch').status_code == 409


def test_uncertain_never_retried_and_restart_recovery(client):
    c, *_ = setup(client)
    launch(client, c)
    with SessionLocal() as db:
        db.scalar(select(OutboundEmail)).status = 'sending'; db.commit()
    assert not work().called
    with SessionLocal() as db:
        assert db.scalar(select(OutboundEmail)).status == 'uncertain'
        assert db.scalar(select(EmailCampaign)).status == 'failed'


def test_safe_retries_rate_limits_and_sender_change(client):
    c, *_ = setup(client)
    launch(client, c)
    failed = MagicMock(return_value=('failed', 'Pre-submission connection failed', True))
    work(failed)
    with SessionLocal() as db:
        job = db.scalar(select(OutboundEmail)); assert job.status == 'queued' and job.attempts == 1
        job.due_at = utcnow() - timedelta(seconds=1)
        db.get(EmailConfiguration, 1).hourly_limit = 1; db.commit()
    assert not work().called
    with SessionLocal() as db:
        config = db.get(EmailConfiguration, 1); config.hourly_limit = 50; config.sender_email = 'changed@example.org'; db.commit()
    assert not work().called
    assert client.get(f"/api/campaigns/{c['id']}").json()['status'] == 'paused'
    assert act(client, c, 'resume').status_code == 409


def test_contact_deletion_and_manual_stop(client):
    c, _, contact, org = setup(client)
    launch(client, c)
    detail = client.get(f"/api/campaigns/{c['id']}").json()
    recipient = detail['recipients'][0]
    assert post(client, f"/campaigns/{c['id']}/recipients/{recipient['id']}/outcome", {'outcome': 'interested'}).status_code == 200
    assert not work().called
    assert post(client, f"/organizations/{org['id']}/contacts/{contact['id']}", method='delete').status_code == 204
    assert client.get(f"/api/campaigns/{c['id']}").json()['recipients'][0]['outgoing']


def test_unthreaded_optout_and_sync_failures(client, monkeypatch):
    c, *_ = setup(client)
    launch(client, c); work()
    with SessionLocal() as db:
        message = EmailMessage(); message['From'] = 'contact@example.org'; message['Subject'] = 'unsubscribe'
        message.set_content('Remove me please')
        ingest(db, message.as_bytes(), 'optout'); db.commit()
        assert db.scalar(select(EmailSuppression)).email == 'contact@example.org'
        assert db.scalar(select(CampaignRecipient)).outcome == 'do_not_contact'
        monkeypatch.setattr('app.campaign_worker.imaplib.IMAP4_SSL', MagicMock(side_effect=OSError('private provider error')))
        sync_mailbox(db, db.get(EmailConfiguration, 1))
        state = db.get(MailboxSyncState, 1)
        assert state.error and 'private' not in state.error


def test_worker_duplicate_job_constraint(client):
    c, *_ = setup(client)
    launch(client, c)
    with SessionLocal() as db:
        original = db.scalar(select(OutboundEmail))
        db.add(OutboundEmail(recipient_id=original.recipient_id, step=0, subject='Duplicate', body='Duplicate', message_id='<duplicate@example.org>', due_at=utcnow()))
        with pytest.raises(IntegrityError):
            db.commit()
    assert work().called
    assert not work().called


def test_smtp_transport_states_and_threading(client, monkeypatch):
    c, *_ = setup(client)
    launch(client, c)
    smtp = MagicMock(); smtp.send_message.return_value = {}
    monkeypatch.setattr('app.campaign_worker.smtplib.SMTP_SSL', MagicMock(return_value=smtp))
    with SessionLocal() as db:
        config = db.get(EmailConfiguration, 1); job = db.scalar(select(OutboundEmail)); recipient = db.scalar(select(CampaignRecipient))
        assert deliver(config, job, recipient, None)[0] == 'accepted'
        message = smtp.send_message.call_args.args[0]
        assert message['Message-ID'] == job.message_id and not message.is_multipart()
        smtp.send_message.side_effect = TimeoutError()
        assert deliver(config, job, recipient, job)[0] == 'uncertain'
        assert smtp.send_message.call_args.args[0]['In-Reply-To'] == job.message_id
        smtp.login.side_effect = OSError()
        assert deliver(config, job, recipient, None) == ('failed', 'Connection or authentication failed before submission', True)


def test_worker_lock_excludes_overlap(client):
    setup(client)
    with engine.connect() as first, engine.connect() as second:
        first.execute(text('SELECT pg_advisory_lock(98171623)'))
        try:
            assert second.scalar(text('SELECT pg_try_advisory_lock(98171623)')) is False
        finally:
            first.execute(text('SELECT pg_advisory_unlock(98171623)'))


def test_safe_rendering():
    result, missing = render('{{contact_name}} {{__import__("os")}}', {'contact_name': '<script>alert(1)</script>'})
    assert result.startswith('<script>')  # Stored and sent as plain text, never evaluated or rendered as HTML.
    assert missing


def test_imap_sync_uid_checkpoint_and_replay(client, monkeypatch):
    c, *_ = setup(client)
    launch(client, c); work()
    with SessionLocal() as db:
        first = db.scalar(select(OutboundEmail).where(OutboundEmail.step == 0))
        message = EmailMessage(); message['From'] = 'contact@example.org'; message['Subject'] = 'Re: outreach'
        message['In-Reply-To'] = first.message_id; message['Message-ID'] = '<imap-reply@example.org>'
        message.set_content('Please send details')
        raw = message.as_bytes(); header, body = raw.split(b'\n\n', 1)
        mailbox = MagicMock(); mailbox.select.return_value = ('OK', [b'1'])
        mailbox.response.return_value = ('UIDVALIDITY', [b'77'])
        def fetch(operation, *args):
            if operation == 'search':
                assert 'SINCE' in args
                return 'OK', [b'1']
            if 'HEADER' in args[-1]:
                return 'OK', [(b'1 (UID 1 BODY[HEADER])', header + b'\n\n')]
            return 'OK', [(b'1 (UID 1 BODY[TEXT])', body)]
        mailbox.uid.side_effect = fetch
        monkeypatch.setattr('app.campaign_worker.imaplib.IMAP4_SSL', MagicMock(return_value=mailbox))
        config = db.get(EmailConfiguration, 1)
        sync_mailbox(db, config)
        state = db.get(MailboxSyncState, 1)
        assert state.last_uid == 1 and state.last_success and state.error is None
        assert db.scalar(select(func.count()).select_from(InboundEmail)) == 1
        assert db.scalar(select(OutboundEmail).where(OutboundEmail.step == 1)).status == 'cancelled'
        # Re-encrypting the same username must not reset the mailbox identity.
        previous = state.identity
        config.imap_username_encrypted = encrypt('sender@example.org'); db.commit()
        sync_mailbox(db, config)
        assert state.identity == previous
        assert db.scalar(select(func.count()).select_from(InboundEmail)) == 1


def test_staff_campaign_read_access_and_explicit_launch_permission(client):
    c, _, contact, _ = setup(client, role='Staff', steps=False)
    from app.models import Role, Permission
    with SessionLocal() as db:
        staff = db.scalar(select(User))
        other = User(full_name='Other staff', email='other@example.org', password_hash='unused', roles=[db.scalar(select(Role).where(Role.name == 'Staff'))])
        db.add(other); db.flush()
        hidden = EmailCampaign(name='Private campaign', objective='Partnership', owner_id=other.id, subject='Private', body='Private')
        db.add(hidden); db.commit(); hidden_id = hidden.id
    assert client.get(f'/api/campaigns/{hidden_id}').status_code == 200
    assert len(client.get('/api/campaigns').json()['items']) == 2
    # Reading company campaigns does not grant another employee's write access.
    assert post(client, f'/campaigns/{hidden_id}/actions', dict(action='submit', version=1)).status_code == 403
    assert post(client, f'/campaigns/{hidden_id}/actions', dict(action='launch', version=1)).status_code == 403
    assert act(client, c, 'submit').status_code == 200
    with SessionLocal() as db:
        campaign = db.get(EmailCampaign, UUID(c['id'])); campaign.status = 'approved'; campaign.approved_version = campaign.version
        db.commit()
    assert act(client, c, 'launch').status_code == 403
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.name == 'Staff'))
        role.permissions.append(db.scalar(select(Permission).where(Permission.code == 'campaigns.launch'))); db.commit()
    assert act(client, c, 'launch').status_code == 200


def test_campaign_read_granted_and_revoked_on_existing_session(client):
    c, _, _, _ = setup(client, role='Staff', steps=False)
    from app.models import Role, Permission
    with SessionLocal() as db:
        actor = db.scalar(select(User))
        actor.responsibilities = []
        role = db.scalar(select(Role).where(Role.name == 'Staff'))
        role.permissions = [p for p in role.permissions if p.code != 'campaigns.read']
        db.commit()
    assert client.get('/api/campaigns').status_code == 403
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.name == 'Staff'))
        role.permissions.append(db.scalar(select(Permission).where(Permission.code == 'campaigns.read')))
        db.commit()
    assert client.get(f"/api/campaigns/{c['id']}").status_code == 200
    assert 'campaigns.read' in client.get('/api/auth/me').json()['permissions']


def test_pause_keeps_schedule_and_reply_checking_stops_followups(client):
    c, *_ = setup(client)
    launch(client, c); work(); due_and_healthy()
    with SessionLocal() as db:
        before = db.scalar(select(OutboundEmail).where(OutboundEmail.step == 1)).due_at
    assert act(client, c, 'pause').status_code == 200
    assert not work().called
    with SessionLocal() as db:
        assert db.scalar(select(OutboundEmail).where(OutboundEmail.step == 1)).due_at == before
        first = db.scalar(select(OutboundEmail).where(OutboundEmail.step == 0))
        message = EmailMessage(); message['From'] = 'contact@example.org'; message['In-Reply-To'] = first.message_id
        message['Subject'] = 'Re: outreach'; message.set_content('Interested')
        ingest(db, message.as_bytes(), 'reply-while-paused'); db.commit()
        assert db.scalar(select(OutboundEmail).where(OutboundEmail.step == 1)).status == 'cancelled'
    assert act(client, c, 'resume').status_code == 200
    assert not work().called


def test_runtime_health_reports_offline_and_actual_worker_cycle(client, monkeypatch):
    from app.campaign_worker import tick
    c, *_ = setup(client)
    assert client.get('/api/campaigns/runtime').json()['running'] is False
    launch(client, c)
    smtp = MagicMock(); smtp.send_message.return_value = {}
    monkeypatch.setattr('app.campaign_worker.smtplib.SMTP_SSL', MagicMock(return_value=smtp))
    mailbox = MagicMock(); mailbox.select.return_value = ('OK', [b'0'])
    mailbox.response.return_value = ('UIDVALIDITY', [b'12'])
    mailbox.uid.return_value = ('OK', [b''])
    monkeypatch.setattr('app.campaign_worker.imaplib.IMAP4_SSL', MagicMock(return_value=mailbox))
    tick()
    state = client.get('/api/campaigns/runtime').json()
    assert state['running'] and state['last_completed'] and state['mailbox_last_success']
    assert state['phase'] == 'idle' and not state['error'] and not state['mailbox_error']
    assert smtp.send_message.call_count == 1
    assert smtp.send_message.call_args.kwargs['to_addrs'] == ['contact@example.org']
    assert smtp.send_message.call_args.args[0]['To'] == 'contact@example.org'
    tick()  # The accepted initial email must not be sent again.
    assert smtp.send_message.call_count == 1


def test_api_starts_delivery_loop_and_launch_wakes_it(client, monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from app.main import app, settings
    from app.models import CampaignWorkerState
    c, *_ = setup(client, steps=False)
    smtp = MagicMock(); smtp.send_message.return_value = {}
    monkeypatch.setattr('app.campaign_worker.smtplib.SMTP_SSL', MagicMock(return_value=smtp))
    mailbox = MagicMock(); mailbox.select.return_value = ('OK', [b'0'])
    mailbox.response.return_value = ('UIDVALIDITY', [b'1']); mailbox.uid.return_value = ('OK', [b''])
    monkeypatch.setattr('app.campaign_worker.imaplib.IMAP4_SSL', MagicMock(return_value=mailbox))
    monkeypatch.setattr(settings, 'campaign_worker_enabled', True)
    def wait_for(check):
        end = time.monotonic() + 8
        while time.monotonic() < end:
            with SessionLocal() as db:
                if check(db):
                    return
            time.sleep(.05)
        pytest.fail('Automatic delivery did not complete')
    with TestClient(app):
        wait_for(lambda db: db.get(CampaignWorkerState, 1) and db.get(CampaignWorkerState, 1).last_completed)
        launch(client, c)  # No manual worker command: this wakes the API-owned loop.
        wait_for(lambda db: db.get(EmailCampaign, UUID(c['id'])).status == 'completed')
        assert smtp.send_message.call_count == 1
        assert client.get(f"/api/campaigns/{c['id']}").json()['sent'] == 1
    from app.services.campaign_runtime import runner
    assert not runner.thread.is_alive()


def test_gmail_all_mail_recovers_reply_without_scanning_old_bodies(client, monkeypatch):
    c, *_ = setup(client)
    launch(client, c); work()
    with SessionLocal() as db:
        config = db.get(EmailConfiguration, 1)
        config.imap_host = 'imap.gmail.com'
        db.add(MailboxSyncState(id=1, identity='old-full-inbox-scanner', uid_validity='1', last_uid=3194,
                               error='Mailbox catch-up in progress; follow-ups are held.'))
        db.commit()
        first = db.scalar(select(OutboundEmail).where(OutboundEmail.step == 0))
        reply = EmailMessage(); reply['Message-ID'] = '<gmail-reply@example.org>'
        reply['In-Reply-To'] = first.message_id; reply['References'] = first.message_id
        reply['From'] = 'contact@example.org'; reply['Subject'] = 'Re: outreach'
        reply.set_content('Yes, I received your campaign.')
        reply_header, reply_body = reply.as_bytes().split(b'\n\n', 1)
        own = EmailMessage(); own['Message-ID'] = first.message_id; own['From'] = config.sender_email
        own['Subject'] = 'Campaign message'
        unrelated = b'Message-ID: <unrelated@example.org>\r\nFrom: news@example.org\r\n\r\n'
        mailbox = MagicMock(); mailbox.capabilities = (b'IMAP4rev1', b'X-GM-EXT-1')
        mailbox.list.return_value = ('OK', [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren \\All) "/" "[Gmail]/Tous les messages"'])
        mailbox.select.return_value = ('OK', [b'40000']); mailbox.response.return_value = ('UIDVALIDITY', [b'7'])
        def fetch(operation, *args):
            if operation == 'search':
                assert 'SINCE' in args and args[-1] == '1:*'
                return 'OK', [b'40000 40001 40002']
            if 'HEADER' in args[-1]:
                return 'OK', [(b'1 (UID 40000 BODY[HEADER])', unrelated),
                    (b'2 (UID 40001 BODY[HEADER])', own.as_bytes()),
                    (b'3 (UID 40002 BODY[HEADER])', reply_header + b'\n\n')]
            assert args[0] == '40002', 'Only the actual reply body should be fetched'
            return 'OK', [(b'3 (UID 40002 BODY[TEXT])', reply_body)]
        mailbox.uid.side_effect = fetch
        monkeypatch.setattr('app.campaign_worker.imaplib.IMAP4_SSL', MagicMock(return_value=mailbox))
        sync_mailbox(db, config)
        mailbox.select.assert_called_once_with(b'"[Gmail]/Tous les messages"', readonly=True)
        state = db.get(MailboxSyncState, 1)
        assert state.last_uid == 40002 and state.last_success and not state.error
        assert db.scalar(select(func.count()).select_from(InboundEmail)) == 1
        assert db.scalar(select(InboundEmail)).body.strip() == 'Yes, I received your campaign.'
        assert db.scalar(select(CampaignRecipient)).outcome == 'replied'
        assert db.scalar(select(OutboundEmail).where(OutboundEmail.step == 1)).status == 'cancelled'


def test_gmail_outgoing_thread_messages_do_not_count_as_replies(client):
    c, *_ = setup(client)
    launch(client, c); work()
    with SessionLocal() as db:
        first = db.scalar(select(OutboundEmail).where(OutboundEmail.step == 0))
        sent_copy = EmailMessage(); sent_copy['From'] = 'sender@example.org'
        sent_copy['Message-ID'] = '<another-company-message@example.org>'
        sent_copy['In-Reply-To'] = first.message_id
        sent_copy.set_content('Our own sent message in Gmail All Mail')
        ingest(db, sent_copy.as_bytes(), 'gmail-sent-copy', 'sender@example.org'); db.commit()
        assert db.scalar(select(func.count()).select_from(InboundEmail)) == 0
        assert not db.scalar(select(CampaignRecipient)).stopped
