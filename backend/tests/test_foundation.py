from datetime import timedelta

import pyotp
from sqlalchemy import select

from app.core.security import digest
from app.db.session import SessionLocal
from app.models import AuditEvent, Contact, Organization, PartnerProfile, Session, User, utcnow
from conftest import authenticate, create_user, csrf, post


def org(client, name="Verification Organization", **extra):
    return post(client, "/organizations", {"name": name, "country": "Cameroon", "classifications": ["prospect"], **extra})


def test_health_and_empty_database(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == response.json()["schema"] == "ready"
    assert "password" not in response.text.lower()
    with SessionLocal() as db:
        assert db.scalar(select(User)) is None
    assert client.get("/api/dashboard").status_code == 401


def test_password_and_mfa_required_before_business_access(client):
    _, password = create_user()
    wrong = post(client, "/auth/login", {"email": "ceo@example.org", "password": "wrong"})
    assert wrong.status_code == 401
    login = post(client, "/auth/login", {"email": "ceo@example.org", "password": password})
    assert login.json()["session_state"] == "enrollment_required"
    assert client.get("/api/organizations").status_code == 403
    secret = post(client, "/auth/mfa/enroll").json()["secret"]
    assert post(client, "/auth/mfa/confirm", {"code": "000000"}).status_code == 400
    old_cookie = client.cookies.get("ntech_session")
    assert post(client, "/auth/mfa/confirm", {"code": pyotp.TOTP(secret).now()}).status_code == 200
    assert client.cookies.get("ntech_session") != old_cookie
    assert client.get("/api/organizations").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(Session).where(Session.token_hash == digest(old_cookie))) is None
        user = db.scalar(select(User))
        assert user.mfa_secret != secret and user.password_hash != password


def test_recovery_code_single_use_and_totp_replay(client):
    _, password, secret, codes = authenticate(client)
    assert post(client, "/auth/logout").status_code == 204
    post(client, "/auth/login", {"email": "ceo@example.org", "password": password})
    assert client.get("/api/dashboard").status_code == 403
    assert post(client, "/auth/mfa/verify", {"code": pyotp.TOTP(secret).now()}).status_code == 400
    assert post(client, "/auth/mfa/verify", {"code": codes[0]}).status_code == 200
    post(client, "/auth/logout")
    post(client, "/auth/login", {"email": "ceo@example.org", "password": password})
    assert post(client, "/auth/mfa/verify", {"code": codes[0]}).status_code == 400
    assert post(client, "/auth/mfa/verify", {"code": codes[1]}).status_code == 200


def test_csrf_and_origin_enforced(client):
    authenticate(client)
    assert client.post("/api/organizations", json={"name": "Blocked"}).status_code == 403
    assert client.post("/api/organizations", json={"name": "Blocked"}, headers={**csrf(client), "Origin": "https://evil.example"}).status_code == 403
    assert org(client).status_code == 201
    assert client.get("/api/organizations").headers["cache-control"] == "no-store"


def test_organization_lifecycle_filters_and_real_dashboard(client):
    authenticate(client)
    assert client.get("/api/dashboard").json()["total_organizations"] == 0
    created = org(client, classifications=["prospect", "partner", "customer"], industry="Technology")
    assert created.status_code == 201, created.text
    organization_id = created.json()["id"]
    with SessionLocal() as db:
        assert db.scalar(select(PartnerProfile)) is not None
    assert org(client, name="  VERIFICATION   ORGANIZATION ").status_code == 409
    assert client.get("/api/organizations?q=verification&classification=partner&country=Cameroon").json()["total"] == 1
    assert client.get("/api/organizations?classification=supplier").json()["total"] == 0
    updated = post(client, f"/organizations/{organization_id}", {"name": "Updated Relationship", "classifications": ["customer"]}, method="put")
    assert updated.status_code == 200
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["total_organizations"] == dashboard["total_customers"] == dashboard["total_staff"] == 1
    assert dashboard["total_partners"] == 0
    assert len(client.get(f"/api/organizations/{organization_id}/activity").json()) == 2
    assert post(client, f"/organizations/{organization_id}", method="delete").status_code == 204
    assert client.get(f"/api/organizations/{organization_id}").status_code == 404
    assert client.get("/api/dashboard").json()["total_organizations"] == 0
    with SessionLocal() as db:
        assert db.scalar(select(Organization)).is_archived is True
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "organization.archived")) is not None


def test_contacts_edit_delete_primary_and_duplicates(client):
    authenticate(client)
    oid = org(client).json()["id"]
    base = f"/organizations/{oid}/contacts"
    first = post(client, base, {"full_name": "First Contact", "email": "first@example.org", "is_primary": True})
    second = post(client, base, {"full_name": "Second Contact", "email": "second@example.org", "is_primary": True})
    assert first.status_code == second.status_code == 201
    assert post(client, base, {"full_name": "Duplicate Contact", "email": "SECOND@example.org"}).status_code == 409
    contacts = client.get(f"/api/organizations/{oid}").json()["contacts"]
    assert sum(c["is_primary"] for c in contacts) == 1
    edited = post(client, f"{base}/{first.json()['id']}", {"full_name": "Changed Contact", "is_primary": True}, method="put")
    assert edited.status_code == 200
    assert post(client, f"{base}/{second.json()['id']}", method="delete").status_code == 204
    assert client.get(f"/api/organizations/{oid}").json()["contact_count"] == 1


def test_staff_responsibilities_and_row_access(client):
    authenticate(client)
    protected_id = org(client).json()["id"]
    post(client, "/auth/logout")
    authenticate(client, "staff@example.org", "Staff", ["Business Development", "Project Operations"])
    me = client.get("/api/auth/me").json()
    assert "organizations.create" in me["permissions"] and "projects.read" in me["permissions"]
    assert client.get("/api/organizations").json()["total"] == 0
    assert client.get(f"/api/organizations/{protected_id}").status_code == 404
    assert org(client, "Assigned Staff Organization").status_code == 201
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["total_organizations"] == 1 and dashboard["total_staff"] is None
    assert client.get("/api/staff").status_code == 403
    assert client.get("/api/access").status_code == 403


def test_manager_finance_permission_and_configurable_access(client):
    authenticate(client, "manager@example.org", "Manager")
    assert "finance.read" in client.get("/api/auth/me").json()["permissions"]
    assert client.get("/api/access").status_code == 403
    assert post(client, "/staff", {"full_name": "Blocked", "email": "blocked@example.org", "temporary_password": "longpassword123!"}).status_code == 403


def test_staff_provision_activation_and_temporary_password(client):
    authenticate(client)
    created = post(client, "/staff", {"full_name": "New Team Member", "email": "new@example.org", "temporary_password": "Initial private password!", "responsibilities": ["Business Development"]})
    assert created.status_code == 201 and created.json()["must_change_password"] is True
    user_id = created.json()["id"]
    assert post(client, f"/staff/{user_id}", {"full_name": "New Team Member", "is_active": False, "role": "Staff", "responsibilities": []}, method="put").status_code == 200
    assert post(client, "/auth/login", {"email": "new@example.org", "password": "Initial private password!"}).status_code == 401


def test_required_password_change_and_session_revocation(client):
    _, password, _, _ = authenticate(client, temporary=True)
    assert org(client).status_code == 403
    assert post(client, "/auth/password", {"current_password": password, "new_password": "My newly chosen private password!"}).status_code == 200
    assert org(client).status_code == 201
    assert post(client, "/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_deactivation_revokes_existing_sessions(client):
    user_id, _, _, _ = authenticate(client, "staff@example.org", "Staff", ["Business Development"])
    staff_token = client.cookies.get("ntech_session")
    post(client, "/auth/logout")
    authenticate(client)
    assert post(client, f"/staff/{user_id}", {"full_name": "Verification User", "is_active": False, "role": "Staff", "responsibilities": []}, method="put").status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(Session).where(Session.token_hash == digest(staff_token))) is None
    client.cookies.clear()
    client.cookies.set("ntech_session", staff_token)
    assert client.get("/api/auth/me").status_code == 401


def test_role_permissions_can_change_without_frontend_trust(client):
    authenticate(client)
    roles = client.get("/api/access").json()["roles"]
    ceo = next(r for r in roles if r["name"] == "CEO")
    manager = next(r for r in roles if r["name"] == "Manager")
    assert post(client, f"/access/roles/{ceo['id']}", {"permissions": []}, method="put").status_code == 400
    assert post(client, f"/access/roles/{manager['id']}", {"permissions": ["dashboard.read"]}, method="put").status_code == 200
    post(client, "/auth/logout")
    authenticate(client, "manager@example.org", "Manager")
    assert client.get("/api/staff").status_code == 403


def test_expired_session_and_last_ceo_protection(client):
    user_id, _, _, _ = authenticate(client)
    assert post(client, f"/staff/{user_id}", {"full_name": "Verification User", "is_active": False, "role": "Staff", "responsibilities": []}, method="put").status_code == 400
    with SessionLocal() as db:
        session = db.scalar(select(Session))
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/organizations").status_code == 401


def test_login_rate_limit_and_validation_redaction(client):
    for _ in range(8):
        assert post(client, "/auth/login", {"email": "missing@example.org", "password": "invalid"}).status_code == 401
    assert post(client, "/auth/login", {"email": "missing@example.org", "password": "invalid"}).status_code == 429
    secret = "do-not-echo-this-secret"
    response = post(client, "/auth/login", {"email": "invalid-email", "password": secret})
    assert response.status_code == 422 and secret not in response.text
