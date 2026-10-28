import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update, text

from app.api.dependencies import DB, require
from app.core.permissions import effective_permissions
from app.core.security import audit
from app.models import AuditEvent, Classification, Contact, Organization, PartnerProfile, User
from app.schemas import ClassificationName, ContactInput, OrganizationInput
from app.services.serialization import audit_json, contact_json, organization_json

router = APIRouter(prefix="/organizations", tags=["Organizations"])
ReadUser = Annotated[User, Depends(require("organizations.read"))]
WriteUser = Annotated[User, Depends(require("organizations.update"))]
ContactUser = Annotated[User, Depends(require("contacts.write"))]


def scoped(query, user):
    query = query.where(Organization.is_archived.is_(False))
    if "organizations.all" not in effective_permissions(user):
        query = query.where(Organization.owner_id == user.id)
    return query


def get_organization(db, user, organization_id):
    org = db.scalar(scoped(select(Organization).where(Organization.id == organization_id), user))
    if not org:
        raise HTTPException(404, "Organization not found")
    return org


def apply_organization(db, user, org, data):
    values = data.model_dump(exclude={"classifications", "owner_id"})
    values["website"] = str(data.website) if data.website else None
    values["email"] = str(data.email).casefold() if data.email else None
    for key, value in values.items():
        setattr(org, key, value)
    org.normalized_name = " ".join(unicodedata.normalize("NFKC", data.name).casefold().split())
    if len(org.normalized_name) < 2:
        raise HTTPException(422, "Organization name needs at least two characters")
    org.classifications = list(db.scalars(select(Classification).where(Classification.name.in_(data.classifications))))
    if len(org.classifications) != len(data.classifications):
        raise HTTPException(503, "Organization classifications have not been initialized")
    owner_id = data.owner_id or (org.owner_id if org.owner_id else user.id)
    if "organizations.all" not in effective_permissions(user) and owner_id != user.id:
        raise HTTPException(403, "You can only assign organizations to yourself")
    owner = db.get(User, owner_id)
    if not owner or not owner.is_active:
        raise HTTPException(422, "Choose an active relationship owner")
    org.owner_id = owner_id
    if "partner" in data.classifications and not org.partner_profile:
        org.partner_profile = PartnerProfile()


@router.get("")
def list_organizations(db: DB, user: ReadUser, q: str = Query(default="", max_length=180),
                       classification: ClassificationName | None = None, country: str | None = Query(default=None, max_length=100),
                       industry: str | None = Query(default=None, max_length=100), page: int = Query(default=1, ge=1),
                       page_size: int = Query(default=12, ge=1, le=100), sort: Literal["recent", "name"] = "recent"):
    query = scoped(select(Organization), user)
    if q.strip():
        query = query.where(Organization.name.icontains(q.strip(), autoescape=True))
    if classification:
        query = query.where(Organization.classifications.any(Classification.name == classification))
    if country:
        query = query.where(Organization.country == country)
    if industry:
        query = query.where(Organization.industry == industry)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    order = Organization.name.asc() if sort == "name" else Organization.created_at.desc()
    items = db.scalars(query.order_by(order, Organization.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [organization_json(o) for o in items], "total": total, "page": page, "page_size": page_size}


@router.get("/filters")
def filters(db: DB, user: ReadUser):
    return {"countries": list(db.scalars(scoped(select(Organization.country).distinct(), user).order_by(Organization.country))),
            "industries": list(db.scalars(scoped(select(Organization.industry).where(Organization.industry.is_not(None)).distinct(), user).order_by(Organization.industry)))}


@router.post("", status_code=201)
def create_organization(data: OrganizationInput, db: DB, user: Annotated[User, Depends(require("organizations.create"))]):
    org = Organization(created_by_id=user.id)
    apply_organization(db, user, org, data)
    db.add(org)
    db.flush()
    audit(db, user, "organization.created", "organization", org.id, org.id, name=org.name)
    db.commit()
    return organization_json(org, detail=True)


@router.get("/{organization_id}")
def organization_detail(organization_id: UUID, db: DB, user: ReadUser):
    return organization_json(get_organization(db, user, organization_id), detail=True)


@router.put("/{organization_id}")
def edit_organization(organization_id: UUID, data: OrganizationInput, db: DB, user: WriteUser):
    db.execute(text('SELECT pg_advisory_xact_lock(98171623)'))
    org = get_organization(db, user, organization_id)
    apply_organization(db, user, org, data)
    audit(db, user, "organization.updated", "organization", org.id, org.id, name=org.name)
    db.commit()
    return organization_json(org, detail=True)


@router.delete("/{organization_id}", status_code=204)
def archive_organization(organization_id: UUID, db: DB, user: WriteUser):
    db.execute(text('SELECT pg_advisory_xact_lock(98171623)'))
    org = get_organization(db, user, organization_id)
    org.is_archived = True
    audit(db, user, "organization.archived", "organization", org.id, org.id, name=org.name)
    db.commit()


@router.get("/{organization_id}/activity")
def activity(organization_id: UUID, db: DB, user: ReadUser, page: int = Query(default=1, ge=1)):
    get_organization(db, user, organization_id)
    records = db.execute(select(AuditEvent, User.full_name).outerjoin(User, User.id == AuditEvent.actor_id)
                         .where(AuditEvent.organization_id == organization_id).order_by(AuditEvent.created_at.desc()).offset((page-1)*30).limit(30))
    return [audit_json(event, name) for event, name in records]


def save_contact(db, user, org, data, contact=None):
    db.execute(text('SELECT pg_advisory_xact_lock(98171623)'))
    if data.is_primary:
        db.execute(update(Contact).where(Contact.organization_id == org.id).values(is_primary=False))
    is_new = contact is None
    if is_new:
        contact = Contact(organization_id=org.id)
        db.add(contact)
    for key, value in data.model_dump().items():
        setattr(contact, key, str(value).casefold() if key == "email" and value else value)
    db.flush()
    audit(db, user, "contact.created" if is_new else "contact.updated", "contact", contact.id, org.id, name=contact.full_name)
    db.commit()
    return contact_json(contact)


@router.post("/{organization_id}/contacts", status_code=201)
def add_contact(organization_id: UUID, data: ContactInput, db: DB, user: ContactUser):
    org = get_organization(db, user, organization_id)
    return save_contact(db, user, org, data)


@router.put("/{organization_id}/contacts/{contact_id}")
def edit_contact(organization_id: UUID, contact_id: UUID, data: ContactInput, db: DB, user: ContactUser):
    org = get_organization(db, user, organization_id)
    contact = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.organization_id == org.id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    return save_contact(db, user, org, data, contact)


@router.delete("/{organization_id}/contacts/{contact_id}", status_code=204)
def delete_contact(organization_id: UUID, contact_id: UUID, db: DB, user: ContactUser):
    db.execute(text('SELECT pg_advisory_xact_lock(98171623)'))
    org = get_organization(db, user, organization_id)
    contact = db.scalar(select(Contact).where(Contact.id == contact_id, Contact.organization_id == org.id))
    if not contact:
        raise HTTPException(404, "Contact not found")
    audit(db, user, "contact.deleted", "contact", contact.id, org.id, name=contact.full_name)
    db.delete(contact)
    db.commit()
