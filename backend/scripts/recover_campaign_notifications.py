"""Recover missing campaign alerts after an outdated server missed their events.

Dry-run by default. Reuses the normal recipient rules and never changes campaigns.
Existing recipient/kind/campaign alerts are preserved rather than duplicated.
"""
import argparse
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from app.db.session import SessionLocal
from app.models import AuditEvent, EmailCampaign, Notification, User
from app.services.notifications import campaign_event


def recover(db, since, until):
    db.execute(text('SELECT pg_advisory_xact_lock(98171623)'))
    events = db.scalars(select(AuditEvent).where(
        AuditEvent.action.in_(['campaign.submit', 'campaign.approve', 'campaign.reject']),
        AuditEvent.created_at >= since, AuditEvent.created_at <= until,
    ).order_by(AuditEvent.created_at, AuditEvent.id)).all()
    existing = {(n.recipient_id, n.kind, n.path) for n in db.scalars(select(Notification).where(
        Notification.kind.in_(['campaign.submitted', 'campaign.submit', 'campaign.approve', 'campaign.reject'])))}
    count = 0
    for event in events:
        campaign = db.get(EmailCampaign, event.entity_id)
        actor = db.get(User, event.actor_id)
        if not campaign or not actor:
            continue
        # Keep candidates in memory until duplicate detection is complete.
        with db.no_autoflush:
            before = set(db.new)
            campaign_event(db, campaign, actor, event.action.split('.')[1])
            for notification in set(db.new) - before:
                key = (notification.recipient_id, notification.kind, notification.path)
                if key in existing:
                    db.expunge(notification)
                else:
                    existing.add(key)
                    notification.created_at = notification.updated_at = event.created_at
                    count += 1
    db.flush()
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', required=True, type=datetime.fromisoformat)
    parser.add_argument('--until', required=True, type=datetime.fromisoformat)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if not args.since.tzinfo or not args.until.tzinfo or args.until < args.since:
        parser.error('Provide an ordered time range with explicit timezone offsets')
    with SessionLocal() as db:
        count = recover(db, args.since, args.until)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(f'{"Recovered" if args.apply else "Would recover"} {count} missing notifications; no campaign states changed.')


if __name__ == '__main__':
    main()
