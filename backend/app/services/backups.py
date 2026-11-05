"""Single-host encrypted backups with a durable queue and PostgreSQL worker lock."""
import shutil
import logging
from datetime import timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.backup import create_backup, encryption
from app.core.config import get_settings
from app.core.security import audit
from app.db.session import engine
from app.models import BackupRun, BackupSchedule, utcnow

QUEUE_LOCK = 98171640
WORKER_LOCK = 98171641
# Cameroon is UTC+1 year-round; no host timezone or Windows tzdata dependency.
DOUALA = timezone(timedelta(hours=1), 'Africa/Douala')


def next_monday(now):
    local = now.astimezone(DOUALA)
    result = local.replace(hour=12, minute=0, second=0, microsecond=0) + timedelta(days=(7-local.weekday()) % 7)
    if result <= local:
        result += timedelta(days=7)
    return result.astimezone(timezone.utc)


def readiness():
    try:
        encryption()
    except (SystemExit, ValueError, TypeError):
        return 'Set a valid BACKUP_ENCRYPTION_KEY on the server before creating backups.'
    if not all(shutil.which(tool) for tool in ('pg_dump', 'pg_restore')):
        return 'Install PostgreSQL backup tools and add them to the server PATH.'
    if not get_settings().backup_worker_enabled:
        return 'The backup worker is disabled on this server.'
    return None


def lock_queue(db):
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': QUEUE_LOCK})


def schedule(db, now):
    row = db.get(BackupSchedule, 1)
    if row is None:
        row = BackupSchedule(id=1, next_run=next_monday(now))
        db.add(row)
        db.flush()
    return row


def active(db):
    return db.scalar(select(BackupRun).where(BackupRun.status.in_(['queued', 'running'])).order_by(BackupRun.created_at))


def archive_path(row):
    directory = get_settings().backup_directory.resolve()
    path = (directory / (row.filename or '')).resolve()
    if path.parent != directory or not row.filename or not path.is_file():
        raise FileNotFoundError('Backup file is unavailable')
    return path


def expire_old(db):
    # Delete only registered, successfully verified archives, keeping eight most recent.
    rows = list(db.scalars(select(BackupRun).where(BackupRun.status == 'completed').order_by(BackupRun.created_at.desc())))
    for row in rows[8:]:
        try:
            path = archive_path(row)
            path.unlink()
            path.with_suffix('.enc.sha256').unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        row.status = 'expired'
    db.commit()


def tick():
    # Keep the session-level lock on a dedicated connection across commits and pg_dump.
    with engine.connect() as connection:
        if not connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': WORKER_LOCK}):
            connection.rollback()
            return
        connection.commit()
        try:
            with Session(bind=connection, expire_on_commit=False) as db:
                now = utcnow()
                lock_queue(db)
                state = schedule(db, now)
                state.heartbeat = now
                # Owning the lock proves any previous running job lost its worker.
                for stale in db.scalars(select(BackupRun).where(BackupRun.status == 'running')):
                    stale.status, stale.finished_at, stale.error = 'failed', now, 'Backup interrupted. Create a new backup.'
                    audit(db, None, 'backup.failed', 'backup', stale.id)
                job = active(db)
                if state.next_run <= now and not job:
                    job = BackupRun(trigger='scheduled')
                    db.add(job)
                    state.next_run = next_monday(now)
                if job:
                    job.status = 'running'
                db.commit()
                if not job:
                    expire_old(db)
                    return
                try:
                    issue = readiness()
                    if issue:
                        raise RuntimeError(issue)
                    output = create_backup(get_settings().backup_directory)
                    job.filename, job.size_bytes = output.name, output.stat().st_size
                    job.status = 'completed'
                except (Exception, SystemExit) as exc:
                    logging.getLogger('ntech').error('backup_failed type=%s', type(exc).__name__)
                    job.status = 'failed'
                    job.error = readiness() or 'Backup failed. Check server storage, database access and PostgreSQL tool versions, then retry.'
                job.finished_at = utcnow()
                audit(db, None, f'backup.{job.status}', 'backup', job.id)
                db.commit()
                if job.status == 'completed':
                    expire_old(db)
        finally:
            connection.rollback()
            connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': WORKER_LOCK})
            connection.commit()
