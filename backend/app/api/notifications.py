from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update

from app.api.dependencies import CurrentSession, DB
from app.core.permissions import effective_permissions
from app.models import Notification, User, utcnow

router = APIRouter(prefix='/notifications', tags=['Notifications'])


def authenticated(session: CurrentSession):
    if session.state != 'authenticated' or session.user.must_change_password:
        raise HTTPException(403, 'Complete account security setup first')
    return session.user


Actor = Annotated[User, Depends(authenticated)]


def visible(actor):
    # Always scope by the authenticated recipient, never a client-supplied user ID.
    clauses = [Notification.recipient_id == actor.id,
               or_(Notification.required_permission.is_(None),
                   Notification.required_permission.in_(effective_permissions(actor)))]
    if not any(role.name in ('CEO', 'Manager') for role in actor.roles):
        clauses.append(Notification.reviewer_only.is_(False))
    return clauses


@router.get('')
def inbox(db: DB, actor: Actor, page: int = Query(default=1, ge=1),
          page_size: int = Query(default=20, ge=1, le=100), unread_only: bool = False):
    scope = visible(actor)
    unread = db.scalar(select(func.count()).select_from(Notification).where(*scope, Notification.read_at.is_(None)))
    filters = [*scope, *([Notification.read_at.is_(None)] if unread_only else [])]
    rows = db.scalars(select(Notification).where(*filters).order_by(Notification.created_at.desc(), Notification.id.desc())
                      .offset((page - 1) * page_size).limit(page_size))
    return dict(items=[dict(id=n.id, kind=n.kind, title=n.title, message=n.message, path=n.path,
                           created_at=n.created_at, read_at=n.read_at) for n in rows],
                total=db.scalar(select(func.count()).select_from(Notification).where(*filters)),
                unread_count=unread, page=page, page_size=page_size)


@router.post('/read-all', status_code=204)
def read_all(db: DB, actor: Actor):
    db.execute(update(Notification).where(*visible(actor), Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()


@router.post('/{id}/read', status_code=204)
def read_one(id: UUID, db: DB, actor: Actor):
    row = db.scalar(select(Notification).where(*visible(actor), Notification.id == id).with_for_update())
    if not row:
        raise HTTPException(404, 'Notification not found')
    if row.read_at is None:
        row.read_at = utcnow()
    db.commit()
