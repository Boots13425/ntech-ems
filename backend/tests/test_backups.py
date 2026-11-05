from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, text

from conftest import authenticate, post
from app import backup
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.models import AuditEvent, BackupRun, BackupSchedule, utcnow
from app.services import backups


@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr(get_settings(), 'backup_directory', tmp_path)
    monkeypatch.setattr(get_settings(), 'backup_worker_enabled', True)
    return tmp_path


@pytest.mark.parametrize('now,expected', [
    ('2026-11-02T10:59:59+00:00', '2026-11-02T11:00:00+00:00'),
    ('2026-11-02T11:00:00+00:00', '2026-11-09T11:00:00+00:00'),
    ('2026-11-08T23:30:00+00:00', '2026-11-09T11:00:00+00:00'),
])
def test_monday_noon_cameroon(now, expected):
    assert backups.next_monday(datetime.fromisoformat(now)).isoformat() == expected


def test_manual_real_archive_download_and_tamper(client, configured, tmp_path):
    authenticate(client)
    assert post(client, '/backups').status_code == 202
    assert post(client, '/backups').status_code == 409
    backups.tick()
    result = client.get('/api/backups').json()
    row = result['runs'][0]
    assert row['status'] == 'completed', row
    response = client.get(f"/api/backups/{row['id']}/download")
    checksum = client.get(f"/api/backups/{row['id']}/download?checksum=true")
    assert response.status_code == checksum.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert len(checksum.text) == 64
    with SessionLocal() as db:
        path = backups.archive_path(db.get(BackupRun, row['id']))
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == 'backup.requested'))
    plain = tmp_path / 'verify.dump'
    backup.verified_plaintext(path, plain)
    assert plain.read_bytes().startswith(b'PGDMP')
    path.write_bytes(response.content + b'corruption')
    with pytest.raises(SystemExit, match='checksum'):
        backup.verified_plaintext(path, plain)


def test_permissions_and_csrf(client, configured):
    assert client.get('/api/backups').status_code == 401
    authenticate(client, role='Staff')
    assert client.get('/api/backups').status_code == 403
    assert post(client, '/backups').status_code == 403
    assert client.get('/api/backups/00000000-0000-0000-0000-000000000000/download').status_code == 403


def test_ceo_csrf_and_missing_key(client, configured, monkeypatch):
    authenticate(client)
    assert client.post('/api/backups').status_code == 403
    monkeypatch.setenv('BACKUP_ENCRYPTION_KEY', 'invalid-key')
    assert post(client, '/backups').status_code == 409
    assert 'BACKUP_ENCRYPTION_KEY' in client.get('/api/backups').json()['issue']


def test_catch_up_once_and_worker_exclusion(configured):
    with SessionLocal() as db:
        db.add(BackupSchedule(id=1, next_run=utcnow() - timedelta(days=10)))
        db.commit()
    with engine.connect() as connection:
        connection.execute(text('SELECT pg_advisory_lock(:key)'), {'key': backups.WORKER_LOCK})
        connection.commit()
        try:
            backups.tick()
            with SessionLocal() as db:
                assert db.scalar(select(BackupRun)) is None
        finally:
            connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': backups.WORKER_LOCK})
            connection.commit()
    backups.tick()
    backups.tick()
    with SessionLocal() as db:
        rows = list(db.scalars(select(BackupRun)))
        assert len(rows) == 1 and rows[0].trigger == 'scheduled' and rows[0].status == 'completed'
        assert db.get(BackupSchedule, 1).next_run > utcnow()


def test_interrupted_and_failure_redaction(configured, monkeypatch):
    with SessionLocal() as db:
        db.add_all([BackupRun(trigger='manual', status='running'), BackupRun(trigger='manual')])
        db.commit()
    def fail(directory):
        raise RuntimeError('SECRET_PASSWORD must never reach history')
    monkeypatch.setattr(backups, 'create_backup', fail)
    backups.tick()
    with SessionLocal() as db:
        rows = list(db.scalars(select(BackupRun)))
        assert all(row.status == 'failed' for row in rows)
        assert all('SECRET_PASSWORD' not in row.error for row in rows)
        assert any('interrupted' in row.error for row in rows)


def test_retention_preserves_eight_and_unregistered_files(configured):
    unrelated = configured / 'unrelated.enc'
    unrelated.write_bytes(b'keep')
    with SessionLocal() as db:
        for i in range(10):
            path = configured / f'archive-{i}.dump.enc'
            path.write_bytes(b'encrypted')
            path.with_suffix('.enc.sha256').write_text('hash')
            db.add(BackupRun(trigger='manual', status='completed', filename=path.name, created_at=utcnow() + timedelta(seconds=i)))
        db.commit()
        backups.expire_old(db)
        assert len(list(db.scalars(select(BackupRun).where(BackupRun.status == 'completed')))) == 8
        assert len(list(db.scalars(select(BackupRun).where(BackupRun.status == 'expired')))) == 2
    assert unrelated.exists()
    assert not (configured / 'archive-0.dump.enc').exists()
    assert not (configured / 'archive-0.dump.enc.sha256').exists()


def test_failed_dump_never_publishes(configured, monkeypatch):
    def fail(program, args, environment):
        Path(args[-1]).write_bytes(b'partial plaintext')
        raise SystemExit('dump failed')
    monkeypatch.setattr(backup, 'run', fail)
    with pytest.raises(SystemExit):
        backup.create_backup(configured)
    assert not list(configured.iterdir())


def test_download_path_escape_and_expired(client, configured):
    authenticate(client)
    with SessionLocal() as db:
        row = BackupRun(trigger='manual', status='completed', filename='../outside.dump.enc')
        db.add(row)
        db.commit()
        run_id = row.id
    assert client.get(f'/api/backups/{run_id}/download').status_code == 404
