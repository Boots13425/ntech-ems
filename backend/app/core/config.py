from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[2] / ".env", extra="ignore")
    app_env: str = "development"
    database_url: SecretStr
    test_database_url: SecretStr | None = None
    mfa_encryption_key: SecretStr
    allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    cookie_secure: bool = True
    session_hours: int = 8
    public_url: str = "http://127.0.0.1:5173"
    smtp_encryption_key: SecretStr | None = None
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"
    smtp_sender_name: str = "NTECH EMS"
    smtp_sender_email: str = ""
    smtp_username: SecretStr = SecretStr("")
    smtp_password: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_security(self):
        Fernet(self.mfa_encryption_key.get_secret_value().encode())
        if self.smtp_encryption_key:
            Fernet(self.smtp_encryption_key.get_secret_value().encode())
        if not self.database_url.get_secret_value().startswith("postgresql+psycopg://"):
            raise ValueError("PostgreSQL with the psycopg driver is required")
        if self.app_env == "production" and (not self.cookie_secure or not self.public_url.startswith("https://")):
            raise ValueError("Production requires HTTPS and secure cookies")
        if "*" in self.allowed_origins:
            raise ValueError("Explicit allowed origins are required")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
