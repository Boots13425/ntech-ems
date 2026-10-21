from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from app.api.dependencies import DB, require
from app.core.config import get_settings
from app.core.security import audit, rate_limit
from app.models import EmailConfiguration, User
from app.services.email_configuration import ConfigurationInput, TestEmailInput, encrypt, public_configuration, run_smtp

router = APIRouter(prefix="/settings/email", tags=["Email configuration"])


def require_ceo(user: Annotated[User, Depends(require("access.manage"))]):
    if not any(role.name == "CEO" for role in user.roles):
        raise HTTPException(403, "Only the CEO can manage email configuration")
    return user


CEO = Annotated[User, Depends(require_ceo)]


@router.get("")
def read_configuration(db: DB, actor: CEO):
    return public_configuration(db)


@router.put("")
def save_configuration(data: ConfigurationInput, db: DB, actor: CEO):
    db.execute(text("SELECT pg_advisory_xact_lock(98171622)"))
    row = db.get(EmailConfiguration, 1)
    if (row.updated_at if row else None) != data.updated_at:
        raise HTTPException(409, "Email configuration changed. Reload the page before saving.")
    previous_username = public_configuration(db)["username"]
    password = data.password.get_secret_value() if data.password else ""
    if row is None:
        row = EmailConfiguration(id=1, password_encrypted=encrypt(get_settings().smtp_password.get_secret_value()))
        db.add(row)
    if data.clear_password:
        row.password_encrypted = None
    elif password:
        row.password_encrypted = encrypt(password)
    elif data.username != previous_username and data.username:
        raise HTTPException(422, "Enter a password when changing the SMTP username")
    if data.username and not row.password_encrypted:
        raise HTTPException(422, "Enter a password for SMTP authentication")
    if not data.username:
        if password:
            raise HTTPException(422, "Enter a username for SMTP authentication")
        row.password_encrypted = None
    changed = [field for field in ("host", "port", "security", "sender_name", "sender_email") if getattr(row, field) != getattr(data, field)]
    if data.username != previous_username:
        changed.append("username")
    if password or data.clear_password or not data.username:
        changed.append("password")
    for field in ("host", "port", "security", "sender_name", "sender_email"):
        setattr(row, field, str(getattr(data, field)) if field == "sender_email" else getattr(data, field))
    row.username_encrypted = encrypt(data.username)
    audit(db, actor, "email.configuration_updated", "email_configuration", changed_fields=changed)
    db.commit()
    return public_configuration(db)


def perform_test(db, actor, recipient=None):
    rate_limit(db, f"smtp-test:{actor.id}", limit=10)
    row = db.get(EmailConfiguration, 1)
    if not row:
        raise HTTPException(409, "Save the email configuration before testing")
    action = "email.test_sent" if recipient else "email.connection_tested"
    try:
        run_smtp(row, recipient)
    except HTTPException:
        audit(db, actor, action, "email_configuration", success=False)
        db.commit()
        raise
    audit(db, actor, action, "email_configuration", success=True)
    db.commit()
    return {"message": "Test email accepted by the SMTP server. Check the recipient inbox and spam folder." if recipient else "SMTP connection and authentication succeeded."}


@router.post("/test-connection")
def test_connection(db: DB, actor: CEO):
    return perform_test(db, actor)


@router.post("/send-test")
def send_test(data: TestEmailInput, db: DB, actor: CEO):
    return perform_test(db, actor, str(data.recipient))
