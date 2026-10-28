from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, text

from app.api.dependencies import DB, require
from app.api.organizations import scoped
from app.core.permissions import effective_permissions
from app.core.security import audit, set_temporary_password
from app.models import AuditEvent, Classification, Organization, Permission, Responsibility, Role, Session, User
from app.schemas import RolePermissions, StaffCreate, StaffUpdate
from app.services.notifications import notify
from app.services.serialization import audit_json, user_json

router = APIRouter(tags=["Management"])
Admin = Annotated[User, Depends(require("staff.manage"))]
AccessAdmin = Annotated[User, Depends(require("access.manage"))]


@router.get("/dashboard")
def dashboard(db: DB, user: Annotated[User, Depends(require("dashboard.read"))]):
    permissions = effective_permissions(user)
    org_ids = scoped(select(Organization.id), user)
    can_read = "organizations.read" in permissions
    total = db.scalar(select(func.count()).select_from(org_ids.subquery())) if can_read else None
    counts = {}
    for name in ["customer", "partner", "prospect"]:
        counts[name] = db.scalar(select(func.count()).select_from(scoped(select(Organization.id).where(Organization.classifications.any(Classification.name == name)), user).subquery())) if can_read else None
    staff = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))) if "staff.read" in permissions else None
    events = db.execute(select(AuditEvent, User.full_name).outerjoin(User, User.id == AuditEvent.actor_id)
                        .where(AuditEvent.organization_id.in_(org_ids)).order_by(AuditEvent.created_at.desc()).limit(8)).all() if can_read else []
    return {"total_organizations": total, "total_customers": counts["customer"], "total_partners": counts["partner"],
            "total_prospects": counts["prospect"], "total_staff": staff, "recent_activity": [audit_json(e, n) for e, n in events],
            "scope": "company" if "organizations.all" in permissions else "assigned"}


@router.get("/staff")
def staff(db: DB, user: Annotated[User, Depends(require("staff.read"))], page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), q: str = Query(default="", max_length=150)):
    query = select(User)
    if q.strip():
        query = query.where(User.full_name.icontains(q.strip(), autoescape=True))
    return {"items": [user_json(u) for u in db.scalars(query.order_by(User.full_name).offset((page-1)*page_size).limit(page_size))],
            "total": db.scalar(select(func.count()).select_from(query.subquery())), "page": page, "page_size": page_size}


def assign_access(db, user, role_name, names):
    role = db.scalar(select(Role).where(Role.name == role_name))
    responsibilities = list(db.scalars(select(Responsibility).where(Responsibility.name.in_(set(names)))))
    if not role or len(responsibilities) != len(set(names)):
        raise HTTPException(422, "Choose valid roles and responsibilities")
    user.roles = [role]
    user.responsibilities = responsibilities


@router.post("/staff", status_code=201)
def create_staff(data: StaffCreate, db: DB, actor: Admin):
    user = User(full_name=data.full_name, email=str(data.email).casefold())
    temporary_password = set_temporary_password(user)
    assign_access(db, user, data.role, data.responsibilities)
    db.add(user)
    db.flush()
    notify(db, user.id, "account.created", "Welcome to NTECH EMS", "Your staff account is ready. Review your account details in Settings.")
    audit(db, actor, "staff.created", entity_id=user.id)
    db.commit()
    return {**user_json(user), "temporary_password": temporary_password}


@router.post("/staff/{user_id}/reset-password")
def reset_staff_password(user_id: UUID, db: DB, actor: Admin):
    if not any(role.name == "CEO" for role in actor.roles):
        raise HTTPException(403, "Only the CEO can reset staff passwords")
    if user_id == actor.id:
        raise HTTPException(400, "Change your own password in account settings")
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not user:
        raise HTTPException(404, "Staff member not found")
    if not user.is_active:
        raise HTTPException(400, "Activate this account before resetting its password")
    temporary_password = set_temporary_password(user)
    db.execute(delete(Session).where(Session.user_id == user.id))
    notify(db, user.id, "account.password_reset", "Your password was reset",
           f"{actor.full_name} reset your password. Change the temporary password at sign-in.")
    audit(db, actor, "staff.password_reset", entity_id=user.id)
    db.commit()
    return {**user_json(user), "temporary_password": temporary_password}


@router.put("/staff/{user_id}")
def update_staff(user_id: UUID, data: StaffUpdate, db: DB, actor: Admin):
    db.execute(text("SELECT pg_advisory_xact_lock(98171621)"))
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Staff member not found")
    if user.id == actor.id and (not data.is_active or data.role != "CEO"):
        raise HTTPException(400, "You cannot deactivate yourself or remove your own CEO role")
    if user.is_active and any(r.name == "CEO" for r in user.roles) and (not data.is_active or data.role != "CEO"):
        active_ceos = db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True), User.roles.any(Role.name == "CEO")))
        if active_ceos <= 1:
            raise HTTPException(400, "At least one active CEO account is required")
    changed = (user.full_name != data.full_name or user.is_active != data.is_active
               or {r.name for r in user.roles} != {data.role}
               or {r.name for r in user.responsibilities} != set(data.responsibilities))
    user.full_name, user.is_active = data.full_name, data.is_active
    assign_access(db, user, data.role, data.responsibilities)
    if not user.is_active:
        db.execute(delete(Session).where(Session.user_id == user.id))
    if changed:
        notify(db, user.id, "account.updated", "Your staff account was updated",
               f"{actor.full_name} updated your account details or access. Review your account in Settings.")
    audit(db, actor, "staff.updated", entity_id=user.id, is_active=user.is_active, role=data.role)
    db.commit()
    return user_json(user)


@router.get("/access")
def access(db: DB, actor: AccessAdmin):
    def serialize(item):
        return {"id": item.id, "name": item.name, "permissions": sorted(p.code for p in item.permissions)}
    return {"roles": [serialize(r) for r in db.scalars(select(Role).order_by(Role.name))],
            "responsibilities": [serialize(r) for r in db.scalars(select(Responsibility).order_by(Responsibility.name))],
            "permissions": list(db.scalars(select(Permission.code).order_by(Permission.code)))}


@router.put("/access/roles/{role_id}")
def update_role(role_id: UUID, data: RolePermissions, db: DB, actor: AccessAdmin):
    role = db.get(Role, role_id)
    if not role:
        raise HTTPException(404, "Role not found")
    if role.name == "CEO":
        raise HTTPException(400, "The CEO role retains complete authorized access")
    permissions = list(db.scalars(select(Permission).where(Permission.code.in_(set(data.permissions)))))
    if len(permissions) != len(set(data.permissions)):
        raise HTTPException(422, "Unknown permission")
    changed = {p.code for p in role.permissions} != set(data.permissions)
    role.permissions = permissions
    if changed:
        for member in db.scalars(select(User).where(User.is_active.is_(True), User.roles.any(id=role.id))):
            notify(db, member.id, "account.access_updated", "Your role permissions changed",
                   f"The permissions for your {role.name} role were updated. Your workspace access now reflects this change.")
    audit(db, actor, "access.role_updated", "role", role.id)
    db.commit()
    return {"id": role.id, "name": role.name, "permissions": sorted(p.code for p in permissions)}
