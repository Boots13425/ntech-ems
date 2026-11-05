import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.dependencies import DB, require
from app.core.security import audit
from app.models import BackupRun, User, utcnow
from app.services import backups

router = APIRouter(prefix='/backups', tags=['Backups'])


def require_ceo(user: Annotated[User, Depends(require('access.manage'))]):
    if not any(role.name == 'CEO' for role in user.roles):
        raise HTTPException(403, 'Only the CEO can manage backups')
    return user


CEO = Annotated[User, Depends(require_ceo)]


@router.get('')
def overview(db: DB, actor: CEO):
    backups.lock_queue(db)
    state = backups.schedule(db, utcnow())
    db.commit()
    rows = db.scalars(select(BackupRun).order_by(BackupRun.created_at.desc()).limit(50))
    return {'next_run': state.next_run, 'heartbeat': state.heartbeat, 'issue': backups.readiness(),
            'runs': [{key: getattr(row, key) for key in ('id', 'created_at', 'finished_at', 'trigger', 'status', 'size_bytes', 'error')} for row in rows]}


@router.post('', status_code=202)
def request_backup(db: DB, actor: CEO):
    backups.lock_queue(db)
    if backups.active(db):
        raise HTTPException(409, 'A backup is already queued or running')
    if issue := backups.readiness():
        raise HTTPException(409, issue)
    row = BackupRun(trigger='manual')
    db.add(row)
    db.flush()
    audit(db, actor, 'backup.requested', 'backup', row.id)
    db.commit()
    return {'id': row.id, 'message': 'Backup queued'}


@router.get('/{run_id}/download')
def download(run_id: uuid.UUID, db: DB, actor: CEO, checksum: bool = False):
    row = db.get(BackupRun, run_id)
    if not row or row.status != 'completed':
        raise HTTPException(404, 'Backup is unavailable')
    try:
        path = backups.archive_path(row)
        if checksum:
            path = path.with_suffix('.enc.sha256')
        if not path.is_file():
            raise FileNotFoundError()
    except FileNotFoundError:
        raise HTTPException(404, 'Backup file is unavailable') from None
    audit(db, actor, 'backup.downloaded', 'backup', row.id)
    db.commit()
    return FileResponse(path, filename=path.name, media_type='application/octet-stream')
