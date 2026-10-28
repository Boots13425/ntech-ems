from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime, Field, model_validator
from sqlalchemy import select, func, text, or_

from app.api.dependencies import DB, require
from app.api.organizations import get_organization, scoped
from app.core.permissions import effective_permissions
from app.core.security import audit
from app.models import (Opportunity, OpportunitySource, OpportunityTask, Organization, EmailCampaign,
    CampaignRecipient, AuditEvent, User, utcnow)
from app.schemas import Input
from app.services.notifications import notify
from app.services.opportunities import eligible_owner, get_opportunity, manages, scope
from app.services.serialization import audit_json

router = APIRouter(prefix='/opportunities', tags=['Opportunities'])
Actor = Annotated[User, Depends(require('opportunities.read'))]
Stage = Literal['new', 'qualified', 'proposal', 'negotiation', 'won', 'lost']


def lock(db):
    db.execute(text('SELECT pg_advisory_xact_lock(98171623)'))


class Details(Input):
    title: str = Field(min_length=2, max_length=180)
    stage: Stage = 'new'
    estimated_value: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    currency: Literal['XAF', 'USD', 'EUR', 'GBP'] = 'XAF'
    expected_close: date | None = None
    loss_reason: str = Field(default='', max_length=1000)
    notes: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def loss_required(self):
        if self.stage == 'lost' and not self.loss_reason.strip():
            raise ValueError('A loss reason is required')
        return self


class Create(Details):
    organization_id: UUID
    source_recipient_id: UUID | None = None
    owner_id: UUID | None = None


class Edit(Details):
    version: int = Field(ge=1)


class Assignment(Input):
    owner_id: UUID
    version: int = Field(ge=1)


class TaskInput(Input):
    title: str = Field(min_length=2, max_length=180)
    notes: str = Field(default='', max_length=5000)
    due_at: AwareDatetime


class TaskEdit(TaskInput):
    version: int = Field(ge=1)
    completed: bool = False


def task_json(task):
    return {key: getattr(task, key) for key in ['id', 'title', 'notes', 'due_at', 'completed_at', 'version', 'opportunity_id']}


def record(db, row):
    result = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    result['organization'] = db.get(Organization, row.organization_id).name
    result['owner'] = db.get(User, row.owner_id).full_name if row.owner_id else None
    next_task = db.scalar(select(OpportunityTask).where(OpportunityTask.opportunity_id == row.id,
        OpportunityTask.completed_at.is_(None)).order_by(OpportunityTask.due_at, OpportunityTask.id).limit(1))
    result['next_action'] = task_json(next_task) if next_task else None
    return result


@router.get('/owners')
def owners(db: DB, actor: Actor):
    if not manages(actor):
        raise HTTPException(403, 'Only managers and the CEO assign owners')
    return [dict(id=u.id, full_name=u.full_name) for u in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name))
            if 'opportunities.read' in effective_permissions(u)]


@router.get('/organizations')
def organizations(db: DB, actor: Actor, q: str = Query(default='', max_length=180)):
    query = select(Organization).where(Organization.is_archived.is_(False), Organization.name.icontains(q, autoescape=True))
    if not manages(actor):
        query = scoped(query, actor)
    return [dict(id=o.id, name=o.name) for o in db.scalars(query.order_by(Organization.name).limit(100))]


@router.get('/work')
def work(db: DB, actor: Actor):
    tomorrow = datetime.combine(datetime.now(ZoneInfo('Africa/Douala')).date() + timedelta(days=1), datetime.min.time(), ZoneInfo('Africa/Douala'))
    rows = db.execute(select(OpportunityTask, Opportunity.title).join(Opportunity).where(
        Opportunity.owner_id == actor.id, Opportunity.stage.notin_(['won', 'lost']),
        OpportunityTask.completed_at.is_(None), OpportunityTask.due_at < tomorrow,
    ).order_by(OpportunityTask.due_at).limit(100)).all()
    return dict(items=[dict(**task_json(task), opportunity_title=title, overdue=task.due_at < utcnow()) for task, title in rows])


@router.get('')
def listing(db: DB, actor: Actor, q: str = Query(default='', max_length=180), stage: Stage | None = None,
            filter: Literal['all', 'mine', 'unassigned', 'no_action', 'overdue'] = 'all', page: int = Query(default=1, ge=1)):
    base = scope(select(Opportunity), actor)
    rows = base.where(Opportunity.title.icontains(q, autoescape=True))
    if stage:
        rows = rows.where(Opportunity.stage == stage)
    if filter == 'mine': rows = rows.where(Opportunity.owner_id == actor.id)
    if filter == 'unassigned': rows = rows.where(Opportunity.owner_id.is_(None))
    pending = select(OpportunityTask.opportunity_id).where(OpportunityTask.completed_at.is_(None))
    if filter == 'no_action': rows = rows.where(Opportunity.id.notin_(pending), Opportunity.stage.notin_(['won', 'lost']))
    if filter == 'overdue': rows = rows.where(Opportunity.id.in_(pending.where(OpportunityTask.due_at < utcnow())), Opportunity.stage.notin_(['won', 'lost']))
    totals = dict(db.execute(select(Opportunity.stage, func.count()).where(Opportunity.id.in_(base.with_only_columns(Opportunity.id))).group_by(Opportunity.stage)).all())
    values = db.execute(select(Opportunity.currency, func.sum(Opportunity.estimated_value)).where(
        Opportunity.id.in_(base.with_only_columns(Opportunity.id)), Opportunity.stage.notin_(['won', 'lost'])).group_by(Opportunity.currency)).all()
    by_owner = db.execute(select(User.full_name, Opportunity.stage, func.count()).select_from(Opportunity)
        .outerjoin(User, User.id == Opportunity.owner_id).where(Opportunity.id.in_(base.with_only_columns(Opportunity.id)))
        .group_by(User.full_name, Opportunity.owner_id, Opportunity.stage)).all() if manages(actor) else []
    return dict(items=[record(db, r) for r in db.scalars(rows.order_by(Opportunity.updated_at.desc(), Opportunity.id).offset((page-1)*20).limit(20))],
                total=db.scalar(select(func.count()).select_from(rows.subquery())), page=page, page_size=20,
                stages=totals, pipeline_values={currency: value or 0 for currency, value in values},
                by_owner=[dict(owner=name or 'Unassigned', stage=stage, count=count) for name, stage, count in by_owner])


@router.post('', status_code=201)
def create(data: Create, db: DB, actor: Actor):
    lock(db)
    if data.owner_id and not manages(actor):
        raise HTTPException(403, 'Only managers and the CEO assign owners')
    source = None
    if data.source_recipient_id:
        if 'campaigns.read' not in effective_permissions(actor):
            raise HTTPException(403, 'Campaign access is required')
        source = db.get(CampaignRecipient, data.source_recipient_id)
        if not source or source.organization_id != data.organization_id:
            raise HTTPException(422, 'Select a conversation belonging to this organization')
        if db.get(EmailCampaign, source.campaign_id).status in ('draft', 'pending_approval', 'approved', 'rejected'):
            raise HTTPException(409, 'Create an opportunity from a launched campaign conversation')
        if db.scalar(select(OpportunitySource.id).where(OpportunitySource.recipient_id == source.id)):
            raise HTTPException(409, 'This conversation already has an opportunity')
    organization = db.get(Organization, data.organization_id)
    if not organization or organization.is_archived:
        raise HTTPException(404, 'Organization not found')
    if not source and not manages(actor):
        get_organization(db, actor, data.organization_id)
    if data.owner_id:
        eligible_owner(db, data.owner_id)
    row = Opportunity(**data.model_dump(exclude={'source_recipient_id'}), creator_id=actor.id)
    db.add(row); db.flush()
    if source:
        db.add(OpportunitySource(opportunity_id=row.id, campaign_id=source.campaign_id, recipient_id=source.id))
    if row.owner_id:
        notify(db, row.owner_id, 'opportunity.assigned', 'Opportunity assigned to you', row.title,
               path=f'/opportunities/{row.id}', permission='opportunities.read')
    else:
        for user in db.scalars(select(User).where(User.is_active.is_(True))):
            if manages(user):
                notify(db, user.id, 'opportunity.assignment_needed', 'Opportunity needs an owner', row.title,
                       path=f'/opportunities/{row.id}', permission='opportunities.read', reviewer_only=True)
    audit(db, actor, 'opportunity.created', 'opportunity', row.id, row.organization_id, title=row.title)
    db.commit()
    return record(db, row)


@router.get('/{id}')
def detail(id: UUID, db: DB, actor: Actor):
    row = get_opportunity(db, actor, id)
    result = record(db, row)
    result['can_edit'] = manages(actor) or row.owner_id == actor.id
    result['tasks'] = [task_json(t) for t in db.scalars(select(OpportunityTask).where(OpportunityTask.opportunity_id == id).order_by(OpportunityTask.due_at))]
    source_ids = select(OpportunitySource.campaign_id).where(OpportunitySource.opportunity_id == id)
    result['campaigns'] = [dict(id=c.id, name=c.name, status=c.status) for c in db.scalars(select(EmailCampaign).where(
        or_(EmailCampaign.opportunity_id == id, EmailCampaign.id.in_(source_ids))).order_by(EmailCampaign.created_at.desc()))] if 'campaigns.read' in effective_permissions(actor) else []
    events = db.execute(select(AuditEvent, User.full_name).outerjoin(User, User.id == AuditEvent.actor_id).where(
        AuditEvent.entity_type == 'opportunity', AuditEvent.entity_id == id).order_by(AuditEvent.created_at.desc()).limit(50)).all()
    result['activity'] = [audit_json(event, name) for event, name in events]
    return result


@router.put('/{id}')
def edit(id: UUID, data: Edit, db: DB, actor: Actor):
    lock(db)
    row = get_opportunity(db, actor, id, write=True)
    if data.version != row.version: raise HTTPException(409, 'Opportunity changed. Reload before saving')
    previous_stage = row.stage
    for key, value in data.model_dump(exclude={'version'}).items(): setattr(row, key, value)
    row.version += 1
    if row.stage != previous_stage:
        notify(db, row.owner_id, 'opportunity.stage', 'Opportunity stage changed', f'{row.title}: {row.stage}', path=f'/opportunities/{id}', permission='opportunities.read') if row.owner_id else None
    audit(db, actor, 'opportunity.updated', 'opportunity', id, row.organization_id, from_stage=previous_stage, stage=row.stage)
    db.commit()
    return record(db, row)


@router.post('/{id}/assign')
def assign(id: UUID, data: Assignment, db: DB, actor: Actor):
    if not manages(actor): raise HTTPException(403, 'Only managers and the CEO assign owners')
    lock(db)
    row = get_opportunity(db, actor, id)
    if row.version != data.version: raise HTTPException(409, 'Opportunity changed. Reload before assigning')
    eligible_owner(db, data.owner_id)
    if row.owner_id != data.owner_id:
        old_owner = row.owner_id
        row.owner_id = data.owner_id
        row.version += 1
        for task in db.scalars(select(OpportunityTask).where(OpportunityTask.opportunity_id == id, OpportunityTask.completed_at.is_(None))):
            task.due_notified = task.overdue_notified = False
        notify(db, row.owner_id, 'opportunity.assigned', 'Opportunity assigned to you', row.title, path=f'/opportunities/{id}', permission='opportunities.read')
        audit(db, actor, 'opportunity.assigned', 'opportunity', id, row.organization_id, previous_owner=str(old_owner) if old_owner else None, owner=str(row.owner_id))
    db.commit()
    return record(db, row)


@router.post('/{id}/tasks', status_code=201)
def create_task(id: UUID, data: TaskInput, db: DB, actor: Actor):
    lock(db)
    row = get_opportunity(db, actor, id, write=True)
    if row.stage in ('won', 'lost'): raise HTTPException(409, 'Reopen the opportunity before adding work')
    task = OpportunityTask(opportunity_id=id, **data.model_dump())
    db.add(task); db.flush()
    if row.owner_id and row.owner_id != actor.id:
        notify(db, row.owner_id, 'opportunity.task', 'New follow-up task', f'{task.title} — {row.title}', path=f'/opportunities/{id}', permission='opportunities.read')
    audit(db, actor, 'opportunity.task_created', 'opportunity', id, row.organization_id, task=str(task.id), title=task.title)
    db.commit()
    return task_json(task)


@router.put('/{id}/tasks/{task_id}')
def edit_task(id: UUID, task_id: UUID, data: TaskEdit, db: DB, actor: Actor):
    lock(db)
    row = get_opportunity(db, actor, id, write=True)
    task = db.get(OpportunityTask, task_id)
    if not task or task.opportunity_id != id: raise HTTPException(404, 'Task not found')
    if data.version != task.version: raise HTTPException(409, 'Task changed. Reload before saving')
    if task.due_at != data.due_at or (task.completed_at and not data.completed):
        task.due_notified = task.overdue_notified = False
    task.title, task.notes, task.due_at = data.title, data.notes, data.due_at
    task.completed_at = (task.completed_at or utcnow()) if data.completed else None
    task.version += 1
    audit(db, actor, 'opportunity.task_updated', 'opportunity', id, row.organization_id, task=str(task.id), completed=data.completed)
    db.commit()
    return task_json(task)
