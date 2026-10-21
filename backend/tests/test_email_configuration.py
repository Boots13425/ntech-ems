import smtplib
import ssl
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from conftest import authenticate, create_user, post
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import AuditEvent, EmailConfiguration, Permission, Role
from app.services import email_configuration as service


def payload(**overrides):
    return dict(host="smtp.example.org", port=587, security="starttls", sender_name="Company",
                sender_email="sender@example.org", username="smtp-user", password="smtp-private-secret", **overrides)


def save(client, data=None):
    return post(client, "/settings/email", data or payload(), method="put")


def test_encryption_redaction_preservation_and_stale_save(client, caplog):
    authenticate(client)
    response = save(client)
    assert response.status_code == 200, response.text
    public = response.json()
    assert public["password_configured"] and "password" not in public
    assert "smtp-private-secret" not in response.text
    with SessionLocal() as db:
        row = db.get(EmailConfiguration, 1)
        encrypted = row.password_encrypted
        assert encrypted != "smtp-private-secret" and row.username_encrypted != "smtp-user"
        assert service.decrypt(encrypted) == "smtp-private-secret"
        events = list(db.scalars(select(AuditEvent).where(AuditEvent.action == "email.configuration_updated")))
        assert events and "smtp-private-secret" not in str(events[0].details)
        assert "smtp-user" not in str(events[0].details)
    updated = payload(updated_at=public["updated_at"])
    updated.update(password=None, host="new.example.org")
    response = save(client, updated)
    assert response.status_code == 200
    assert client.get('/api/settings/email').json()['host'] == 'new.example.org'
    with SessionLocal() as db:
        assert db.get(EmailConfiguration, 1).password_encrypted == encrypted
    assert save(client, updated).status_code == 409
    updated.update(updated_at=response.json()['updated_at'], username='', clear_password=True)
    assert save(client, updated).json()['password_configured'] is False
    assert 'smtp-private-secret' not in caplog.text


@pytest.mark.parametrize('field,value', [('host', 'https://bad/'), ('port', 0), ('port', 65536),
    ('security', 'bad'), ('sender_name', 'Injected\r\nBcc: victim@example.org'),
    ('sender_email', 'invalid'), ('username', 'bad\nuser'), ('password', 'x' * 1025)])
def test_validation(client, field, value):
    authenticate(client)
    data = payload()
    data[field] = value
    response = save(client, data)
    assert response.status_code == 422
    assert 'smtp-private-secret' not in response.text
    assert 'x' * 1025 not in response.text


def test_authentication_role_mfa_and_csrf(client):
    assert client.get('/api/settings/email').status_code == 401
    _, password = create_user()
    assert post(client, '/auth/login', {'email': 'ceo@example.org', 'password': password}).status_code == 200
    assert client.get('/api/settings/email').status_code == 403


def test_non_ceo_even_with_access_permission(client):
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.name == 'Manager'))
        role.permissions.append(db.scalar(select(Permission).where(Permission.code == 'access.manage')))
        db.commit()
    authenticate(client, role='Manager')
    assert client.get('/api/settings/email').status_code == 403
    assert save(client).status_code == 403
    assert post(client, '/settings/email/test-connection').status_code == 403
    assert post(client, '/settings/email/send-test', {'recipient': 'test@example.org'}).status_code == 403


def test_saved_configuration_tests_and_safe_errors(client, monkeypatch, caplog):
    authenticate(client)
    assert client.put('/api/settings/email', json=payload()).status_code == 403
    assert post(client, '/settings/email/test-connection').status_code == 409
    assert save(client).status_code == 200
    smtp = MagicMock()
    smtp.noop.return_value = (250, b'OK')
    factory = MagicMock(return_value=smtp)
    monkeypatch.setattr(service.smtplib, 'SMTP', factory)
    assert post(client, '/settings/email/test-connection').status_code == 200
    factory.assert_called_with('smtp.example.org', 587, timeout=10)
    smtp.starttls.assert_called_once()
    context = smtp.starttls.call_args.kwargs['context']
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    smtp.login.assert_called_with('smtp-user', 'smtp-private-secret')
    smtp.send_message.assert_not_called()
    response = post(client, '/settings/email/send-test', {'recipient': 'test@example.org'})
    assert response.status_code == 200
    smtp.send_message.assert_called_once()
    assert smtp.send_message.call_args.kwargs['to_addrs'] == ['test@example.org']
    assert smtp.send_message.call_args.args[0]['From'] == 'Company <sender@example.org>'
    smtp.login.side_effect = smtplib.SMTPAuthenticationError(535, b'smtp-private-secret')
    response = post(client, '/settings/email/test-connection')
    assert response.status_code == 502 and 'smtp-private-secret' not in response.text
    assert 'smtp-private-secret' not in caplog.text
    with SessionLocal() as db:
        assert any(e.details == {'success': False} for e in db.scalars(select(AuditEvent).where(AuditEvent.action == 'email.connection_tested')))


def test_tls_none_defaults_and_immediate_changes(client, monkeypatch):
    authenticate(client)
    monkeypatch.setattr(get_settings(), 'smtp_host', 'default.example.org')
    assert client.get('/api/settings/email').json()['host'] == 'default.example.org'
    data = payload()
    data.update(security='none')
    assert save(client, data).status_code == 422
    data.update(security='tls', port=465)
    saved = save(client, data).json()
    smtp = MagicMock()
    smtp.noop.return_value = (250, b'OK')
    factory = MagicMock(return_value=smtp)
    monkeypatch.setattr(service.smtplib, 'SMTP_SSL', factory)
    assert post(client, '/settings/email/test-connection').status_code == 200
    assert factory.call_args.args == ('smtp.example.org', 465)
    smtp.starttls.assert_not_called()
    data.update(host='relay.example.org', security='none', port=25, username='', password=None,
                clear_password=True, updated_at=saved['updated_at'])
    assert save(client, data).status_code == 200
    assert client.get('/api/settings/email').json()['host'] == 'relay.example.org'
    smtp.reset_mock()
    monkeypatch.setattr(service.smtplib, 'SMTP', factory)
    assert post(client, '/settings/email/test-connection').status_code == 200
    factory.assert_called_with('relay.example.org', 25, timeout=10)
    smtp.login.assert_not_called()


@pytest.mark.parametrize('failure', [TimeoutError(), ssl.SSLError('secret-provider-details'),
    smtplib.SMTPNotSupportedError('secret-provider-details'), smtplib.SMTPRecipientsRefused({'secret-provider-details': (550, b'bad')})])
def test_provider_failures_are_redacted(client, monkeypatch, failure):
    authenticate(client)
    assert save(client).status_code == 200
    monkeypatch.setattr(service.smtplib, 'SMTP', MagicMock(side_effect=failure))
    response = post(client, '/settings/email/test-connection')
    assert response.status_code == 502
    assert 'secret-provider-details' not in response.text


def test_password_rotation_requires_credentials_and_rate_limit(client, monkeypatch):
    authenticate(client)
    saved = save(client).json()
    data = payload(updated_at=saved['updated_at'])
    data.update(username='replacement-user', password=None)
    assert save(client, data).status_code == 422
    data.update(password='replacement-secret')
    assert save(client, data).status_code == 200
    with SessionLocal() as db:
        row = db.get(EmailConfiguration, 1)
        assert service.decrypt(row.password_encrypted) == 'replacement-secret'
        assert service.decrypt(row.username_encrypted) == 'replacement-user'
    smtp = MagicMock()
    smtp.noop.return_value = (250, b'OK')
    monkeypatch.setattr(service.smtplib, 'SMTP', MagicMock(return_value=smtp))
    for _ in range(10):
        assert post(client, '/settings/email/test-connection').status_code == 200
    assert post(client, '/settings/email/test-connection').status_code == 429
    assert smtp.login.call_count == 10


def test_corrupt_credentials_fail_safely(client):
    authenticate(client)
    assert save(client).status_code == 200
    with SessionLocal() as db:
        db.get(EmailConfiguration, 1).password_encrypted = 'corrupt-private-value'
        db.commit()
    response = post(client, '/settings/email/test-connection')
    assert response.status_code == 503
    assert 'corrupt-private-value' not in response.text
