from app.core.permissions import effective_permissions


def user_json(user, state="authenticated"):
    return {"id": str(user.id), "full_name": user.full_name, "email": user.email,
            "roles": [r.name for r in user.roles], "responsibilities": [r.name for r in user.responsibilities],
            "permissions": sorted(effective_permissions(user)), "is_active": user.is_active,
            "mfa_enabled": user.mfa_enabled, "must_change_password": user.must_change_password,
            "session_state": state, "created_at": user.created_at}


def contact_json(contact):
    return {key: getattr(contact, key) for key in ["id", "full_name", "job_title", "email", "phone", "is_primary", "created_at"]}


def organization_json(org, detail=False):
    result = {key: getattr(org, key) for key in ["id", "name", "industry", "country", "city", "email", "phone", "website", "address", "owner_id", "created_by_id", "created_at", "updated_at"]}
    result.update(classifications=[c.name for c in org.classifications], contact_count=len(org.contacts))
    if detail:
        result.update(notes=org.notes, contacts=[contact_json(c) for c in sorted(org.contacts, key=lambda c: (not c.is_primary, c.full_name))])
    return result


def audit_json(event, actor_name=None):
    return {"id": event.id, "action": event.action, "entity_type": event.entity_type,
            "entity_id": event.entity_id, "organization_id": event.organization_id,
            "details": event.details, "created_at": event.created_at, "actor_name": actor_name or "System"}
