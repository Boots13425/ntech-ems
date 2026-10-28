from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.db.session import SessionLocal
from app.models import AuditEvent, Notification, Permission, Role, Session, User
from conftest import authenticate, create_user, post


def test_reset_replaces_password_revokes_sessions_and_preserves_mfa(client):
    staff_id, old_password, _, codes = authenticate(client, 'staff@example.org', 'Staff')
    old_token = client.cookies.get('ntech_session')
    with SessionLocal() as db:
        old_hash = db.get(User, UUID(staff_id)).password_hash
        mfa_secret = db.get(User, UUID(staff_id)).mfa_secret
    client.cookies.clear()
    authenticate(client)
    unrelated, unrelated_password = create_user('unrelated@example.org', 'Staff')
    result = post(client, f'/staff/{staff_id}/reset-password')
    assert result.status_code == 200
    password = result.json()['temporary_password']
    assert password != old_password and len(password) == 24
    assert result.json()['must_change_password'] is True
    assert result.headers['cache-control'] == 'no-store'
    assert password not in client.get('/api/staff').text
    with SessionLocal() as db:
        staff = db.get(User, UUID(staff_id))
        assert staff.password_hash != old_hash
        assert verify_password(password, staff.password_hash)
        assert not verify_password(old_password, staff.password_hash)
        assert staff.mfa_enabled and staff.mfa_secret == mfa_secret
        assert db.scalar(select(Session).where(Session.user_id == staff.id)) is None
        assert verify_password(unrelated_password, db.get(User, UUID(unrelated)).password_hash)
        alerts = db.scalars(select(Notification).where(Notification.kind == 'account.password_reset')).all()
        assert len(alerts) == 1 and alerts[0].recipient_id == staff.id
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == 'staff.password_reset'))
        assert audit.entity_id == staff.id
        assert password not in str(audit.details) and password not in alerts[0].message
    client.cookies.clear()
    client.cookies.set('ntech_session', old_token)
    assert client.get('/api/auth/me').status_code == 401
    client.cookies.clear()
    assert post(client, '/auth/login', {'email': 'staff@example.org', 'password': old_password}).status_code == 401
    login = post(client, '/auth/login', {'email': 'staff@example.org', 'password': password})
    assert login.status_code == 200 and login.json()['session_state'] == 'mfa_required'
    assert post(client, '/auth/mfa/verify', {'code': codes[0]}).status_code == 200
    assert client.get('/api/dashboard').status_code == 403
    assert post(client, '/auth/password', {'current_password': password, 'new_password': 'My replacement private password!'}).status_code == 200
    assert client.get('/api/dashboard').status_code == 200


@pytest.mark.parametrize('role', ['Manager', 'Staff'])
def test_only_ceo_can_reset_even_if_staff_manage_is_granted(client, role):
    authenticate(client, role=role)
    target, _ = create_user('target@example.org', 'Staff')
    with SessionLocal() as db:
        assignment = db.scalar(select(Role).where(Role.name == role))
        assignment.permissions.append(db.scalar(select(Permission).where(Permission.code == 'staff.manage')))
        db.commit()
    assert post(client, f'/staff/{target}/reset-password').status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(Notification)) is None


def test_reset_errors_csrf_and_repeat_reset(client):
    ceo_id, *_ = authenticate(client)
    target, _ = create_user('target@example.org', 'Staff')
    assert client.post(f'/api/staff/{target}/reset-password').status_code == 403
    assert post(client, f'/staff/{ceo_id}/reset-password').status_code == 400
    assert post(client, f'/staff/{uuid4()}/reset-password').status_code == 404
    first = post(client, f'/staff/{target}/reset-password').json()['temporary_password']
    second = post(client, f'/staff/{target}/reset-password').json()['temporary_password']
    assert first != second
    with SessionLocal() as db:
        user = db.get(User, UUID(target))
        assert verify_password(second, user.password_hash) and not verify_password(first, user.password_hash)
        user.is_active = False
        db.commit()
    assert post(client, f'/staff/{target}/reset-password').status_code == 400
    post(client, '/auth/logout')
    assert post(client, f'/staff/{target}/reset-password').status_code == 401
