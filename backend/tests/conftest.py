import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import Settings

configuration = Settings()
if not configuration.test_database_url:
    raise RuntimeError("TEST_DATABASE_URL is required; tests never use the application database")
test_url = configuration.test_database_url.get_secret_value()
if not (make_url(test_url).database or "").endswith("_test") or test_url == configuration.database_url.get_secret_value():
    raise RuntimeError("Tests require a separate database with a name ending in _test")
os.environ["DATABASE_URL"] = test_url
os.environ["COOKIE_SECURE"] = "false"
os.environ["CAMPAIGN_WORKER_ENABLED"] = "false"

from fastapi.testclient import TestClient
from app.core.config import get_settings
get_settings.cache_clear()
from app.core.permissions import seed_access
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import Base


@pytest.fixture(scope="session", autouse=True)
def migrate():
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(migrate):
    with engine.begin() as connection:
        names = ', '.join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
        connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        seed_access(db)
        db.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app, base_url="http://127.0.0.1:5173", headers={"Origin": "http://127.0.0.1:5173"}) as client:
        yield client


def csrf(client):
    return {"X-CSRF-Token": client.cookies.get("ntech_csrf", "")}


def post(client, path, body=None, method="post"):
    return getattr(client, method)(f"/api{path}", json=body, headers=csrf(client)) if method in {"post", "put"} else getattr(client, method)(f"/api{path}", headers=csrf(client))


def create_user(email="ceo@example.org", role="CEO", responsibilities=(), temporary=False):
    from sqlalchemy import select
    from app.core.security import hash_password
    from app.models import Role, Responsibility, User
    password = "A private test password 2026!"
    with SessionLocal() as db:
        user = User(full_name="Verification User", email=email, password_hash=hash_password(password), must_change_password=temporary,
                    roles=[db.scalar(select(Role).where(Role.name == role))],
                    responsibilities=list(db.scalars(select(Responsibility).where(Responsibility.name.in_(responsibilities)))))
        db.add(user)
        db.commit()
        return str(user.id), password


def authenticate(client, email="ceo@example.org", role="CEO", responsibilities=(), temporary=False):
    import pyotp
    user_id, password = create_user(email, role, responsibilities, temporary)
    assert post(client, "/auth/login", {"email": email, "password": password}).status_code == 200
    enrollment = post(client, "/auth/mfa/enroll").json()
    confirmation = post(client, "/auth/mfa/confirm", {"code": pyotp.TOTP(enrollment["secret"]).now()})
    assert confirmation.status_code == 200, confirmation.text
    return user_id, password, enrollment["secret"], confirmation.json()["recovery_codes"]
