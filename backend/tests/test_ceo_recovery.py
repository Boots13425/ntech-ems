import sys

from sqlalchemy import select, func

from app.cli import main
from app.db.session import SessionLocal
from app.models import RecoveryCode, Session, User
from conftest import authenticate, post


def test_ceo_recovery_requires_fresh_enrollment(client, monkeypatch):
    user_id, old_password, secret, codes = authenticate(client)
    password = 'New private recovery password 2026!'
    monkeypatch.setattr(sys, 'argv', ['cli', 'recover-ceo', '--email', 'ceo@example.org'])
    monkeypatch.setattr('app.cli.getpass.getpass', lambda prompt: password)
    main()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == 'ceo@example.org'))
        assert str(user.id) == user_id
        assert not user.mfa_enabled and user.mfa_secret is None
        assert user.mfa_last_counter is None
        assert db.scalar(select(func.count()).select_from(Session)) == 0
        assert db.scalar(select(func.count()).select_from(RecoveryCode)) == 0
    assert client.get('/api/auth/me').status_code == 401
    assert post(client, '/auth/login', {'email': 'ceo@example.org', 'password': old_password}).status_code == 401
    result = post(client, '/auth/login', {'email': 'ceo@example.org', 'password': password})
    assert result.status_code == 200
    assert result.json()['session_state'] == 'enrollment_required'
    assert post(client, '/auth/mfa/enroll').json()['secret'] != secret
