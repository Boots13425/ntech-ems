from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.core.permissions import effective_permissions
from app.core.security import check_csrf, digest
from app.db.session import get_db
from app.models import Session, utcnow

DB = Annotated[DBSession, Depends(get_db)]


def current_session(request: Request, db: DB):
    token = request.cookies.get("ntech_session")
    session = db.scalar(select(Session).where(Session.token_hash == digest(token))) if token else None
    if not session or session.expires_at <= utcnow() or not session.user.is_active:
        raise HTTPException(401, "Please sign in to continue")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_csrf(request, session)
    return session


CurrentSession = Annotated[Session, Depends(current_session)]


def require(permission: str):
    def dependency(session: CurrentSession):
        if session.state != "authenticated":
            raise HTTPException(403, "Complete multifactor authentication first")
        if session.user.must_change_password:
            raise HTTPException(403, "Change your temporary password first")
        if permission not in effective_permissions(session.user):
            raise HTTPException(403, "You do not have permission to perform this action")
        return session.user
    return dependency
