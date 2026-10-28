from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Notification, Role, User
from app.services.notifications import notify
from conftest import authenticate, create_user, post
from test_campaigns import setup, act


def test_submission_targets_only_active_authorized_reviewers(client):
    campaign, *_ = setup(client, role='Staff')
    ceo, _ = create_user('reviewer@example.org', 'CEO')
    manager, _ = create_user('manager@example.org', 'Manager')
    create_user('other-staff@example.org', 'Staff')
    inactive, _ = create_user('inactive@example.org', 'CEO')
    with SessionLocal() as db:
        db.get(User, UUID(inactive)).is_active = False
        db.commit()
    assert act(client, campaign, 'submit').status_code == 200
    assert act(client, campaign, 'submit').status_code == 409
    with SessionLocal() as db:
        rows = db.scalars(select(Notification)).all()
        assert {str(n.recipient_id) for n in rows} == {ceo, manager}
        assert len(rows) == 2
        assert all(n.kind == 'campaign.submitted' for n in rows)
    assert client.get('/api/notifications').json()['total'] == 0


def test_decisions_notify_owner_not_unrelated_staff(client):
    campaign, *_ = setup(client, role='Staff')
    assert act(client, campaign, 'submit').status_code == 200
    post(client, '/auth/logout')
    authenticate(client, 'reviewer@example.org', 'Manager')
    for action in ['reject', 'submit', 'approve']:
        assert act(client, campaign, action).status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == 3
        assert all(str(n.recipient_id) == campaign['owner_id'] for n in rows)
        assert {n.kind for n in rows} == {'campaign.reject', 'campaign.submit', 'campaign.approve'}
    assert client.get('/api/notifications').json()['total'] == 0


def test_inbox_isolation_read_idempotency_pagination_and_csrf(client):
    actor, *_ = authenticate(client)
    other, _ = create_user('other@example.org', 'Staff')
    with SessionLocal() as db:
        for index in range(3):
            notify(db, UUID(actor), 'account.updated', 'My alert', f'Update {index}')
        notify(db, UUID(other), 'account.password_changed', 'Private alert', 'Other account only')
        db.commit()
        foreign = db.scalar(select(Notification).where(Notification.recipient_id == UUID(other))).id
    inbox = client.get('/api/notifications?page_size=2').json()
    assert inbox['total'] == inbox['unread_count'] == 3 and len(inbox['items']) == 2
    second = client.get('/api/notifications?page=2&page_size=2').json()
    assert len(second['items']) == 1
    assert second['items'][0]['id'] not in {n['id'] for n in inbox['items']}
    assert 'Other account only' not in str(inbox)
    assert post(client, f'/notifications/{foreign}/read').status_code == 404
    assert client.post('/api/notifications/read-all').status_code == 403
    own = inbox['items'][0]['id']
    assert post(client, f'/notifications/{own}/read').status_code == 204
    timestamp = client.get('/api/notifications').json()['items'][0]['read_at']
    assert post(client, f'/notifications/{own}/read').status_code == 204
    assert client.get('/api/notifications').json()['items'][0]['read_at'] == timestamp
    assert client.get('/api/notifications?unread_only=true').json()['total'] == 2
    assert post(client, '/notifications/read-all').status_code == 204
    assert client.get('/api/notifications').json()['unread_count'] == 0
    with SessionLocal() as db:
        assert db.get(Notification, foreign).read_at is None
    post(client, '/auth/logout')
    assert client.get('/api/notifications').status_code == 401


def test_password_change_is_private_and_contains_no_credentials(client):
    actor, password, *_ = authenticate(client)
    create_user('unrelated@example.org')
    replacement = 'Replacement private password 2026!'
    assert post(client, '/auth/password', {'current_password': password, 'new_password': replacement}).status_code == 200
    inbox = client.get('/api/notifications').json()
    assert inbox['total'] == 1
    assert inbox['items'][0]['title'] == 'Password changed'
    assert password not in str(inbox) and replacement not in str(inbox)
    with SessionLocal() as db:
        assert {str(n.recipient_id) for n in db.scalars(select(Notification))} == {actor}


def test_changed_permissions_and_roles_hide_old_review_alerts(client):
    actor, *_ = authenticate(client, 'manager@example.org', 'Manager')
    with SessionLocal() as db:
        notify(db, UUID(actor), 'campaign.submitted', 'Review', 'Private campaign',
               permission='campaigns.read', reviewer_only=True)
        db.commit()
        notification_id = db.scalar(select(Notification.id))
        user = db.get(User, UUID(actor))
        user.roles = [db.scalar(select(Role).where(Role.name == 'Staff'))]
        db.commit()
    assert client.get('/api/notifications').json()['total'] == 0
    assert post(client, f'/notifications/{notification_id}/read').status_code == 404
    with SessionLocal() as db:
        user = db.get(User, UUID(actor))
        user.roles = [db.scalar(select(Role).where(Role.name == 'Manager'))]
        user.roles[0].permissions = [p for p in user.roles[0].permissions if p.code != 'campaigns.read']
        db.commit()
    assert client.get('/api/notifications').json()['unread_count'] == 0


def test_staff_access_changes_notify_only_affected_account(client):
    authenticate(client)
    affected, _ = create_user('affected@example.org', 'Staff')
    create_user('bystander@example.org', 'Staff')
    body = {'full_name': 'Changed Name', 'is_active': True, 'role': 'Staff', 'responsibilities': []}
    assert post(client, f'/staff/{affected}', body, method='put').status_code == 200
    assert post(client, f'/staff/{affected}', body, method='put').status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == 1 and str(rows[0].recipient_id) == affected


def test_incomplete_security_cannot_read_notifications(client):
    authenticate(client, temporary=True)
    assert client.get('/api/notifications').status_code == 403
    assert post(client, '/notifications/read-all').status_code == 403


def test_role_permission_alerts_only_reach_members_of_that_role(client):
    authenticate(client)
    affected, _ = create_user('staff@example.org', 'Staff')
    create_user('manager@example.org', 'Manager')
    role = next(r for r in client.get('/api/access').json()['roles'] if r['name'] == 'Staff')
    body = {'permissions': ['dashboard.read']}
    assert post(client, f'/access/roles/{role["id"]}', body, method='put').status_code == 200
    assert post(client, f'/access/roles/{role["id"]}', body, method='put').status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == 1 and str(rows[0].recipient_id) == affected


def test_owner_reviewer_gets_only_one_alert_when_another_manager_submits(client):
    campaign, *_ = setup(client, role='Manager')
    post(client, '/auth/logout')
    authenticate(client, 'other-manager@example.org', 'Manager')
    assert act(client, campaign, 'submit').status_code == 200
    with SessionLocal() as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == 1 and str(rows[0].recipient_id) == campaign['owner_id']


def test_migration_includes_existing_pending_campaigns(client):
    from alembic import command
    from alembic.config import Config
    campaign, *_ = setup(client, role='Staff')
    reviewer, _ = create_user('reviewer@example.org', 'CEO')
    create_user('unrelated@example.org', 'Staff')
    assert act(client, campaign, 'submit').status_code == 200
    # This suite is guarded by conftest to use only the disposable _test database.
    config = Config('alembic.ini')
    command.downgrade(config, '0004_campaign_runtime')
    command.upgrade(config, 'head')
    with SessionLocal() as db:
        rows = db.scalars(select(Notification)).all()
        assert len(rows) == 1
        assert str(rows[0].recipient_id) == reviewer
        assert rows[0].path == f'/campaigns/{campaign["id"]}'
