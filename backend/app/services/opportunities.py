from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import or_, select

from app.core.permissions import effective_permissions
from app.models import Opportunity, OpportunityTask, User, utcnow
from app.services.notifications import notify


def manages(user):
    return any(r.name in ('CEO', 'Manager') for r in user.roles)


def scope(query, user):
    if not manages(user):
        query = query.where(or_(Opportunity.owner_id == user.id,
            (Opportunity.owner_id.is_(None)) & (Opportunity.creator_id == user.id)))
    return query


def get_opportunity(db, user, id, write=False):
    if 'opportunities.read' not in effective_permissions(user):
        raise HTTPException(403, 'Opportunity access is not assigned')
    row = db.scalar(scope(select(Opportunity).where(Opportunity.id == id), user))
    if not row:
        raise HTTPException(404, 'Opportunity not found')
    if write and not manages(user) and row.owner_id != user.id:
        raise HTTPException(403, 'A manager or CEO must assign an owner before work starts')
    return row


def eligible_owner(db, id):
    user = db.get(User, id) if id else None
    if not user or not user.is_active or 'opportunities.read' not in effective_permissions(user):
        raise HTTPException(422, 'Choose an active owner with Opportunities access')
    return user


def remind_tasks(db):
    now = utcnow()
    tasks = db.scalars(select(OpportunityTask).join(Opportunity).where(
        OpportunityTask.completed_at.is_(None), Opportunity.stage.notin_(['won', 'lost']),
        OpportunityTask.due_at <= now + timedelta(hours=24),
        or_(OpportunityTask.due_notified.is_(False), OpportunityTask.overdue_notified.is_(False)),
    ).with_for_update(of=OpportunityTask, skip_locked=True)).all()
    for task in tasks:
        row = db.get(Opportunity, task.opportunity_id)
        user = db.get(User, row.owner_id) if row.owner_id else None
        if not user or not user.is_active or 'opportunities.read' not in effective_permissions(user):
            continue
        overdue = task.due_at < now
        if overdue and task.overdue_notified or not overdue and task.due_notified:
            continue
        notify(db, user.id, 'opportunity.task_overdue' if overdue else 'opportunity.task_due',
               'Follow-up overdue' if overdue else 'Follow-up due soon',
               f'{task.title} — {row.title}', path=f'/opportunities/{row.id}', permission='opportunities.read')
        task.due_notified = True
        if overdue:
            task.overdue_notified = True
