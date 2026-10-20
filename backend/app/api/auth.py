import hmac
import secrets
from uuid import UUID

import pyotp
from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import delete, select

from app.api.dependencies import CurrentSession, DB
from app.core.security import DUMMY_PASSWORD_HASH, audit, check_origin, cipher, digest, hash_password, hasher, issue_session, rate_limit, verify_password
from app.models import RecoveryCode, Session, User, utcnow
from app.schemas import Code, Login, PasswordChange
from app.services.serialization import user_json

router = APIRouter(prefix="/auth", tags=["Authentication"])


def lock_user(db, user):
    return db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))


def verify_totp(user, code):
    if not user.mfa_secret or not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(cipher().decrypt(user.mfa_secret.encode()).decode())
    counter = totp.timecode(utcnow())
    for step in [counter, counter - 1, counter + 1]:
        if hmac.compare_digest(totp.generate_otp(step), code) and step > (user.mfa_last_counter or -1):
            user.mfa_last_counter = step
            return True
    return False


@router.post("/login")
def login(data: Login, request: Request, response: Response, db: DB):
    check_origin(request)
    email = str(data.email).casefold()
    rate_limit(db, f"login-account:{email}")
    rate_limit(db, f"login-ip:{request.client.host if request.client else 'unknown'}", limit=60)
    user = db.scalar(select(User).where(User.email == email))
    valid = verify_password(data.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not valid or not user.is_active:
        audit(db, None, "auth.login_failed")
        db.commit()
        raise HTTPException(401, "Email or password is incorrect")
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(data.password)
    existing_token = request.cookies.get("ntech_session")
    previous = db.scalar(select(Session).where(Session.token_hash == digest(existing_token))) if existing_token else None
    state = "mfa_required" if user.mfa_enabled else "enrollment_required"
    issue_session(db, response, user, state, previous)
    audit(db, user, "auth.password_verified", entity_id=user.id)
    db.commit()
    return user_json(user, state)


@router.get("/me")
def me(session: CurrentSession):
    return user_json(session.user, session.state)


@router.post("/logout", status_code=204)
def logout(response: Response, db: DB, session: CurrentSession):
    audit(db, session.user, "auth.logout", entity_id=session.user_id)
    db.delete(session)
    db.commit()
    for name in ["ntech_session", "ntech_csrf"]:
        response.delete_cookie(name, path="/")


@router.post("/mfa/enroll")
def enroll(db: DB, session: CurrentSession):
    user = lock_user(db, session.user)
    if user.mfa_enabled or session.state != "enrollment_required":
        raise HTTPException(400, "MFA enrollment is not available for this session")
    if not user.mfa_secret:
        user.mfa_secret = cipher().encrypt(pyotp.random_base32().encode()).decode()
        audit(db, user, "auth.mfa_enrollment_started", entity_id=user.id)
        db.commit()
    secret = cipher().decrypt(user.mfa_secret.encode()).decode()
    return {"secret": secret, "uri": pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name="NTECH EMS")}


@router.post("/mfa/confirm")
def confirm(data: Code, response: Response, db: DB, session: CurrentSession):
    rate_limit(db, f"mfa:{session.user_id}")
    user = lock_user(db, session.user)
    if user.mfa_enabled or session.state != "enrollment_required":
        raise HTTPException(400, "MFA enrollment is not available for this session")
    if not verify_totp(user, data.code):
        audit(db, user, "auth.mfa_failed", entity_id=user.id)
        db.commit()
        raise HTTPException(400, "That code is invalid or has already been used")
    user.mfa_enabled = True
    codes = [secrets.token_hex(10) for _ in range(8)]
    for code in codes:
        db.add(RecoveryCode(user_id=user.id, code_hash=digest(code)))
    issue_session(db, response, user, "authenticated", session)
    audit(db, user, "auth.mfa_enabled", entity_id=user.id)
    db.commit()
    return {"user": user_json(user), "recovery_codes": codes}


@router.post("/mfa/verify")
def verify(data: Code, response: Response, db: DB, session: CurrentSession):
    rate_limit(db, f"mfa:{session.user_id}")
    user = lock_user(db, session.user)
    if session.state != "mfa_required" or not user.mfa_enabled:
        raise HTTPException(400, "This session is not waiting for an MFA code")
    recovery = None
    valid = verify_totp(user, data.code)
    if not valid:
        recovery = db.scalar(select(RecoveryCode).where(RecoveryCode.user_id == user.id, RecoveryCode.code_hash == digest(data.code.replace(" ", "").replace("-", "").lower())).with_for_update())
        valid = recovery is not None
    if not valid:
        audit(db, user, "auth.mfa_failed", entity_id=user.id)
        db.commit()
        raise HTTPException(400, "That code is invalid or has already been used")
    if recovery:
        db.delete(recovery)
    issue_session(db, response, user, "authenticated", session)
    audit(db, user, "auth.recovery_code_used" if recovery else "auth.login", entity_id=user.id)
    db.commit()
    return user_json(user)


@router.post("/password")
def change_password(data: PasswordChange, response: Response, db: DB, session: CurrentSession):
    if session.state != "authenticated":
        raise HTTPException(403, "Complete multifactor authentication first")
    rate_limit(db, f"password:{session.user_id}")
    user = lock_user(db, session.user)
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    if data.current_password == data.new_password:
        raise HTTPException(400, "Choose a different password")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    db.execute(delete(Session).where(Session.user_id == user.id, Session.id != session.id))
    issue_session(db, response, user, "authenticated", session)
    audit(db, user, "auth.password_changed", entity_id=user.id)
    db.commit()
    return user_json(user)


@router.get("/sessions")
def sessions(db: DB, session: CurrentSession):
    if session.state != "authenticated":
        raise HTTPException(403, "Complete multifactor authentication first")
    return [{"id": s.id, "created_at": s.created_at, "expires_at": s.expires_at, "current": s.id == session.id}
            for s in db.scalars(select(Session).where(Session.user_id == session.user_id, Session.expires_at > utcnow()).order_by(Session.created_at.desc()))]


@router.delete("/sessions/{session_id}", status_code=204)
def revoke_session(session_id: UUID, db: DB, session: CurrentSession):
    if session.state != "authenticated":
        raise HTTPException(403, "Complete multifactor authentication first")
    target = db.scalar(select(Session).where(Session.id == session_id, Session.user_id == session.user_id))
    if not target:
        raise HTTPException(404, "Session not found")
    db.delete(target)
    audit(db, session.user, "auth.session_revoked", entity_id=session_id)
    db.commit()
