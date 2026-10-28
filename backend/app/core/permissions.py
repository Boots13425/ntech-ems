from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Classification, Permission, Responsibility, Role, User

PERMISSIONS = [
    "dashboard.read", "organizations.read", "organizations.create", "organizations.update", "organizations.all",
    "contacts.write", "partners.read", "customers.read", "staff.read", "staff.manage", "access.manage",
    "campaigns.read", "campaigns.launch", "opportunities.read", "projects.read", "reports.read", "finance.read", "audit.read",
]
ROLE_DEFAULTS = {
    "CEO": PERMISSIONS,
    "Manager": [p for p in PERMISSIONS if p not in {"access.manage", "staff.manage"}],
    "Staff": ["dashboard.read", "campaigns.read"],
}
RESPONSIBILITY_DEFAULTS = {
    "Business Development": ["organizations.read", "organizations.create", "organizations.update", "contacts.write", "customers.read", "opportunities.read"],
    "Partnership Management": ["organizations.read", "organizations.create", "organizations.update", "contacts.write", "partners.read"],
    "Sales and Outreach": ["organizations.read", "organizations.create", "organizations.update", "contacts.write", "customers.read", "campaigns.read", "opportunities.read"],
    "Project Operations": ["organizations.read", "projects.read"],
}


def effective_permissions(user: User) -> set[str]:
    return {p.code for assignment in [*user.roles, *user.responsibilities] for p in assignment.permissions}


def seed_access(db: Session):
    """Only configuration records are seeded. Existing permission choices are preserved."""
    permissions = {p.code: p for p in db.scalars(select(Permission))}
    for code in PERMISSIONS:
        if code not in permissions:
            permissions[code] = Permission(code=code)
            db.add(permissions[code])
    for model, defaults in [(Role, ROLE_DEFAULTS), (Responsibility, RESPONSIBILITY_DEFAULTS)]:
        existing = {r.name for r in db.scalars(select(model))}
        for name, codes in defaults.items():
            if name not in existing:
                db.add(model(name=name, permissions=[permissions[c] for c in codes]))
    existing_classes = set(db.scalars(select(Classification.name)))
    for name in ["prospect", "customer", "partner", "supplier"]:
        if name not in existing_classes:
            db.add(Classification(name=name))
    db.flush()
