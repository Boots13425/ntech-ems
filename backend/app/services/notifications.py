"""Recipient selection belongs on the server, in the event's transaction."""
from sqlalchemy import select

from app.core.permissions import effective_permissions
from app.models import Notification, User, Opportunity, OpportunitySource


def notify(db, recipient_id, kind, title, message, *, path='/settings', permission=None, reviewer_only=False):
    recipient = db.get(User, recipient_id)
    if not recipient or not recipient.is_active:
        return
    if permission and permission not in effective_permissions(recipient):
        return
    db.add(Notification(recipient_id=recipient_id, kind=kind, title=title, message=message,
                        path=path, required_permission=permission, reviewer_only=reviewer_only))


def campaign_event(db, campaign, actor, operation):
    path = f'/campaigns/{campaign.id}'
    opportunity = db.get(Opportunity, campaign.opportunity_id) if campaign.opportunity_id else None
    owner_id = opportunity.owner_id if opportunity else campaign.owner_id
    if operation == 'submit':
        reviewers = db.scalars(select(User).where(User.is_active.is_(True),
            User.id != actor.id, User.id != owner_id,
            User.roles.any(name='CEO') | User.roles.any(name='Manager')))
        for reviewer in reviewers:
            notify(db, reviewer.id, 'campaign.submitted', 'Campaign submitted for approval',
                   f'{actor.full_name} submitted “{campaign.name}” for review.',
                   path=path, permission='campaigns.read', reviewer_only=True)
    labels = {'submit': 'submitted', 'approve': 'approved', 'reject': 'rejected',
              'launch': 'launched', 'pause': 'paused', 'resume': 'resumed', 'cancel': 'cancelled',
              'edit': 'edited'}
    if owner_id and owner_id != actor.id:
        notify(db, owner_id, f'campaign.{operation}', f'Campaign {labels[operation]}',
               f'{actor.full_name} {labels[operation]} your campaign “{campaign.name}”. Open it for details.',
               path=path, permission='campaigns.read')


def campaign_reply(db, campaign, recipient):
    owners = {campaign.owner_id}
    if campaign.opportunity_id:
        owners = {db.get(Opportunity, campaign.opportunity_id).owner_id}
    owners.update(db.scalars(select(Opportunity.owner_id).join(OpportunitySource).where(
        OpportunitySource.recipient_id == recipient.id, Opportunity.stage.notin_(['won', 'lost']))))
    for owner_id in owners - {None}:
        notify(db, owner_id, 'campaign.reply', 'New campaign response',
               f'A response was received for "{campaign.name}". Open the campaign to review it.',
               path=f'/campaigns/{campaign.id}', permission='campaigns.read')
