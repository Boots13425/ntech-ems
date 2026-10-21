"""Read SMTP configuration per operation; never log provider errors or credentials."""
import ipaddress
import re
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator

from app.core.config import get_settings
from app.models import EmailConfiguration


class ConfigurationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535, strict=True)
    security: Literal["starttls", "tls", "none"]
    sender_name: str = Field(min_length=1, max_length=150)
    sender_email: EmailStr = Field(max_length=254)
    username: str = Field(default="", max_length=320)
    password: SecretStr | None = Field(default=None, max_length=1024)
    clear_password: bool = False
    updated_at: datetime | None = None

    @field_validator("host", "sender_name", "sender_email", "username", mode="before")
    @classmethod
    def clean_text(cls, value):
        if isinstance(value, str):
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError("Control characters are not allowed")
            return value.strip()
        return value

    @field_validator("host")
    @classmethod
    def valid_host(cls, value):
        try:
            ipaddress.ip_address(value)
        except ValueError:
            if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in value.split(".")):
                raise ValueError("Enter a hostname or IP address without a URL or port")
        return value

    @model_validator(mode="after")
    def credentials(self):
        if self.clear_password and self.password and self.password.get_secret_value():
            raise ValueError("Choose either replacing or clearing the password")
        if self.security == "none" and self.username:
            raise ValueError("SMTP authentication requires STARTTLS or TLS")
        return self


class TestEmailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipient: EmailStr = Field(max_length=254)


def cipher():
    settings = get_settings()
    # Existing installations can reuse their protected application key.
    key = settings.smtp_encryption_key or settings.mfa_encryption_key
    return Fernet(key.get_secret_value().encode())


def encrypt(value):
    return cipher().encrypt(value.encode()).decode() if value else None


def decrypt(value):
    try:
        return cipher().decrypt(value.encode()).decode() if value else ""
    except (InvalidToken, ValueError):
        raise HTTPException(503, "SMTP credentials cannot be decrypted. Restore the configured encryption key or replace the credentials.") from None


def public_configuration(db):
    row = db.get(EmailConfiguration, 1)
    if row:
        return dict(host=row.host, port=row.port, security=row.security, sender_name=row.sender_name,
                    sender_email=row.sender_email, username=decrypt(row.username_encrypted),
                    password_configured=bool(row.password_encrypted), updated_at=row.updated_at, saved=True)
    settings = get_settings()
    return dict(host=settings.smtp_host, port=settings.smtp_port, security=settings.smtp_security,
                sender_name=settings.smtp_sender_name, sender_email=settings.smtp_sender_email,
                username=settings.smtp_username.get_secret_value(),
                password_configured=bool(settings.smtp_password.get_secret_value()), updated_at=None, saved=False)


def run_smtp(row, recipient=None):
    """Connect and authenticate; optionally submit one fixed test message. No retries."""
    username, password = decrypt(row.username_encrypted), decrypt(row.password_encrypted)
    context = ssl.create_default_context()
    smtp = None
    try:
        if row.security == "tls":
            smtp = smtplib.SMTP_SSL(row.host, row.port, timeout=10, context=context)
        else:
            smtp = smtplib.SMTP(row.host, row.port, timeout=10)
        smtp.ehlo_or_helo_if_needed()
        if row.security == "starttls":
            smtp.starttls(context=context)
            smtp.ehlo()
        if username:
            if row.security == "none":
                raise HTTPException(422, "SMTP authentication requires STARTTLS or TLS")
            smtp.login(username, password)
        if recipient:
            message = EmailMessage()
            message["From"] = formataddr((row.sender_name, row.sender_email))
            message["To"] = recipient
            message["Subject"] = "NTECH EMS test email"
            message.set_content("This test email confirms that NTECH EMS submitted a message using your saved email configuration.")
            smtp.send_message(message, from_addr=row.sender_email, to_addrs=[recipient])
        else:
            code, _ = smtp.noop()
            if code != 250:
                raise smtplib.SMTPException()
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(502, "SMTP authentication failed. Check the username, password, and provider requirements.") from None
    except ssl.SSLError:
        raise HTTPException(502, "SMTP TLS verification failed. Check the host, port, security mode, and server certificate.") from None
    except smtplib.SMTPNotSupportedError:
        raise HTTPException(502, "The SMTP server does not support the selected security or authentication method.") from None
    except (smtplib.SMTPException, OSError, UnicodeError, ValueError):
        raise HTTPException(502, "SMTP operation failed. Check the server, port, sender permissions, and recipient. If sending timed out, check the inbox before retrying.") from None
    finally:
        if smtp:
            # Closing avoids reporting a successful submission as failed if QUIT fails.
            smtp.close()
