import hashlib
import hmac
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request, Response
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.models import AuditEvent, AuthAttempt, Session, User, utcnow

hasher = PasswordHasher()
DUMMY_PASSWORD_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(password: str):
    return hasher.hash(password)


def set_temporary_password(user: User):
    password = secrets.token_urlsafe(18)
    user.password_hash = hash_password(password)
    user.must_change_password = True
    return password


def verify_password(password: str, encoded: str):
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def cipher():
    return Fernet(get_settings().mfa_encryption_key.get_secret_value().encode())


def audit(db: DBSession, actor: User | None, action: str, entity_type: str = "user", entity_id=None, organization_id=None, **details):
    db.add(AuditEvent(actor_id=actor.id if actor else None, action=action, entity_type=entity_type,
                      entity_id=entity_id, organization_id=organization_id, details=details))


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin not in get_settings().allowed_origins:
        raise HTTPException(403, "This request origin is not allowed")


def check_csrf(request: Request, session: Session):
    check_origin(request)
    token = request.headers.get("x-csrf-token", "")
    if not token or not hmac.compare_digest(digest(token), session.csrf_hash):
        raise HTTPException(403, "Your security token has expired. Refresh and try again.")


def issue_session(db: DBSession, response: Response, user: User, state: str, previous: Session | None = None):
    if previous:
        db.delete(previous)
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    settings = get_settings()
    lifetime = timedelta(hours=settings.session_hours) if state == "authenticated" else timedelta(minutes=10)
    session = Session(user_id=user.id, token_hash=digest(token), csrf_hash=digest(csrf), state=state, expires_at=utcnow() + lifetime)
    db.add(session)
    response.set_cookie("ntech_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=int(lifetime.total_seconds()), path="/")
    response.set_cookie("ntech_csrf", csrf, httponly=False, secure=settings.cookie_secure, samesite="lax", max_age=int(lifetime.total_seconds()), path="/")
    return session


def rate_limit(db: DBSession, key: str, limit=8, minutes=15):
    hashed = digest(key)
    # A transaction-scoped lock makes counting/inserting safe across API processes.
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int(hashed[:15], 16)})
    since = utcnow() - timedelta(minutes=minutes)
    db.execute(delete(AuthAttempt).where(AuthAttempt.created_at < utcnow() - timedelta(days=1)))
    count = db.scalar(select(func.count()).select_from(AuthAttempt).where(AuthAttempt.key == hashed, AuthAttempt.created_at > since))
    if count >= limit:
        db.commit()
        raise HTTPException(429, "Too many attempts. Try again in 15 minutes.", headers={"Retry-After": "900"})
    db.add(AuthAttempt(key=hashed))
    db.commit()
