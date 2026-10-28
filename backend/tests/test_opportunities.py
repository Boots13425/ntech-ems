from datetime import timedelta
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Notification, OpportunityTask, User, utcnow
from app.services.opportunities import remind_tasks
from conftest import authenticate, create_user, post
from test_campaigns import setup, launch


def switch(client, cookies):
    client.cookies.clear()
    client.cookies.update(cookies)


def organization(client):
    return post(client, '/organizations', {'name': 'Opportunity company', 'classifications': ['prospect']}).json()


def test_assignment_is_management_only_and_scoped(client):
    staff, *_ = authenticate(client, 'staff@example.org', 'Staff', ['Business Development'])
    org = organization(client)
    body = {'title': 'New business', 'organization_id': org['id']}
    assert post(client, '/opportunities', {**body, 'owner_id': staff}).status_code == 403
    response = post(client, '/opportunities', body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row['owner_id'] is None
    assert post(client, f'/opportunities/{row["id"]}/assign', {'owner_id': staff, 'version': 1}).status_code == 403
    assert post(client, f'/opportunities/{row["id"]}/tasks', {'title': 'Call customer', 'due_at': utcnow().isoformat()}).status_code == 403
    staff_cookies = dict(client.cookies)
    client.cookies.clear()
    authenticate(client, 'manager@example.org', 'Manager')
    assert client.get('/api/opportunities').json()['total'] == 1
    result = post(client, f'/opportunities/{row["id"]}/assign', {'owner_id': staff, 'version': 1})
    assert result.status_code == 200
    assert post(client, f'/opportunities/{row["id"]}/assign', {'owner_id': staff, 'version': 1}).status_code == 409
    manager_cookies = dict(client.cookies)
    switch(client, staff_cookies)
    assert client.get(f'/api/opportunities/{row["id"]}').json()['can_edit']
    assert client.get('/api/notifications').json()['items'][0]['kind'] == 'opportunity.assigned'
    client.cookies.clear()
    stranger, *_ = authenticate(client, 'stranger@example.org', 'Staff')
    stranger_cookies = dict(client.cookies)
    assert client.get('/api/opportunities').json()['total'] == 0
    assert client.get(f'/api/opportunities/{row["id"]}').status_code == 404
    assert client.get('/api/opportunities/owners').status_code == 403
    switch(client, manager_cookies)
    assert post(client, f'/opportunities/{row["id"]}/assign', {'owner_id': stranger, 'version': 2}).status_code == 200
    switch(client, staff_cookies)
    assert client.get(f'/api/opportunities/{row["id"]}').status_code == 404
    assert client.get('/api/notifications').json()['total'] == 0
    switch(client, stranger_cookies)
    assert client.get(f'/api/opportunities/{row["id"]}').status_code == 200


def test_tasks_stages_values_and_due_notifications(client):
    owner, *_ = authenticate(client)
    org = organization(client)
    data = {'title': 'Software proposal', 'organization_id': org['id'], 'owner_id': owner, 'estimated_value': '150000.50'}
    row = post(client, '/opportunities', data).json()
    task_data = {'title': 'Prepare proposal', 'notes': 'Confirm scope', 'due_at': (utcnow() - timedelta(hours=1)).isoformat()}
    task = post(client, f'/opportunities/{row["id"]}/tasks', task_data).json()
    assert client.get('/api/opportunities/work').json()['items'][0]['overdue']
    assert client.get('/api/opportunities?filter=overdue').json()['total'] == 1
    assert client.get('/api/opportunities?filter=no_action').json()['total'] == 0
    with SessionLocal() as db:
        remind_tasks(db); db.commit()
        remind_tasks(db); db.commit()
        alerts = db.scalars(select(Notification).where(Notification.kind == 'opportunity.task_overdue')).all()
        assert len(alerts) == 1
    completed = post(client, f'/opportunities/{row["id"]}/tasks/{task["id"]}', {**task_data, 'version': 1, 'completed': True}, method='put')
    assert completed.status_code == 200
    assert client.get('/api/opportunities/work').json()['items'] == []
    assert post(client, f'/opportunities/{row["id"]}/tasks/{task["id"]}', {**task_data, 'version': 1}, method='put').status_code == 409
    edit = {'title': 'Software proposal', 'stage': 'lost', 'version': 1, 'estimated_value': '150000.50'}
    assert post(client, f'/opportunities/{row["id"]}', edit, method='put').status_code == 422
    assert post(client, f'/opportunities/{row["id"]}', {**edit, 'loss_reason': 'Budget unavailable'}, method='put').status_code == 200
    assert client.get('/api/opportunities').json()['stages']['lost'] == 1
    assert client.get('/api/opportunities').json()['pipeline_values'] == {}
    assert post(client, f'/opportunities/{row["id"]}/tasks', task_data).status_code == 409
    assert client.get(f'/api/opportunities/{row["id"]}').json()['activity']
    assert post(client, '/opportunities', {**data, 'estimated_value': '-1'}).status_code == 422
    assert client.post('/api/opportunities', json=data).status_code == 403


def test_campaign_conversation_conversion_and_outreach_reuses_campaigns(client):
    campaign, payload, contact, org = setup(client)
    launch(client, campaign)
    detail = client.get(f'/api/campaigns/{campaign["id"]}').json()
    staff, _ = create_user('assigned@example.org', 'Staff')
    converted = post(client, '/opportunities', {'title': 'Interested company', 'organization_id': org['id'],
        'source_recipient_id': detail['recipients'][0]['id'], 'owner_id': staff})
    assert converted.status_code == 201, converted.text
    row = converted.json()
    assert post(client, '/opportunities', {'title': 'Duplicate', 'organization_id': org['id'], 'source_recipient_id': detail['recipients'][0]['id']}).status_code == 409
    assert client.get(f'/api/opportunities/{row["id"]}').json()['campaigns'][0]['id'] == campaign['id']
    # Assign to a staff account with no organization ownership: only the opportunity's contacts are available.
    client.cookies.clear()
    import pyotp
    assert post(client, '/auth/login', {'email': 'assigned@example.org', 'password': 'A private test password 2026!'}).status_code == 200
    secret = post(client, '/auth/mfa/enroll').json()['secret']
    assert post(client, '/auth/mfa/confirm', {'code': pyotp.TOTP(secret).now()}).status_code == 200
    contacts = client.get(f'/api/campaigns/contacts?opportunity_id={row["id"]}').json()
    assert len(contacts) == 1 and contacts[0]['id'] == org['id']
    draft = post(client, '/campaigns', {**payload, 'steps': [], 'opportunity_id': row['id']})
    assert draft.status_code == 201, draft.text
    assert draft.json()['opportunity_id'] == row['id']
    assert len(client.get(f'/api/opportunities/{row["id"]}').json()['campaigns']) == 2
    assert post(client, f'/campaigns/{draft.json()["id"]}/actions', {'action': 'submit', 'version': 1}).status_code == 200
    assert post(client, f'/campaigns/{draft.json()["id"]}/actions', {'action': 'approve', 'version': 1}).status_code == 403
    assert post(client, '/campaigns/preview', {'subject': 'Hello', 'body': 'Hello', 'contact_id': contact['id'], 'opportunity_id': row['id']}).status_code == 200


def test_owner_cannot_be_inactive_and_currency_totals_stay_separate(client):
    authenticate(client)
    org = organization(client)
    staff, _ = create_user('inactive@example.org', 'Staff')
    with SessionLocal() as db:
        db.get(User, UUID(staff)).is_active = False
        db.commit()
    data = {'title': 'Company interest', 'organization_id': org['id']}
    assert post(client, '/opportunities', {**data, 'owner_id': staff}).status_code == 422
    assert post(client, '/opportunities', {**data, 'estimated_value': '100', 'currency': 'USD'}).status_code == 201
    assert post(client, '/opportunities', {**data, 'estimated_value': '50000', 'currency': 'XAF'}).status_code == 201
    values = client.get('/api/opportunities').json()['pipeline_values']
    assert float(values['USD']) == 100 and float(values['XAF']) == 50000


def test_worker_reminds_without_email_configuration_and_respects_closed_work(client):
    from app.campaign_worker import tick
    owner, *_ = authenticate(client)
    org = organization(client)
    row = post(client, '/opportunities', {'title': 'Service inquiry', 'organization_id': org['id'], 'owner_id': owner}).json()
    task = post(client, f'/opportunities/{row["id"]}/tasks', {'title': 'Meet the customer', 'due_at': (utcnow() + timedelta(hours=1)).isoformat()}).json()
    tick()
    tick()
    with SessionLocal() as db:
        assert len(db.scalars(select(Notification).where(Notification.kind == 'opportunity.task_due')).all()) == 1
        db.get(OpportunityTask, UUID(task['id'])).due_at = utcnow() - timedelta(hours=1)
        db.commit()
    tick()
    tick()
    with SessionLocal() as db:
        assert len(db.scalars(select(Notification).where(Notification.kind == 'opportunity.task_overdue')).all()) == 1
    assert post(client, f'/opportunities/{row["id"]}', {'title': row['title'], 'stage': 'won', 'version': 1}, method='put').status_code == 200
    assert client.get('/api/opportunities/work').json()['items'] == []


def test_linked_campaign_reassignment_and_contact_boundaries(client):
    ceo, *_ = authenticate(client)
    org = organization(client)
    contact = post(client, f'/organizations/{org["id"]}/contacts', {'full_name': 'Company Contact', 'email': 'person@example.org'}).json()
    other_org = post(client, '/organizations', {'name': 'Other company', 'classifications': ['prospect']}).json()
    foreign = post(client, f'/organizations/{other_org["id"]}/contacts', {'full_name': 'Other Contact', 'email': 'other@example.org'}).json()
    row = post(client, '/opportunities', {'title': 'Linked work', 'organization_id': org['id'], 'owner_id': ceo}).json()
    payload = {'name': 'Linked draft', 'objective': 'General Outreach', 'subject': 'Hello', 'body': 'Meeting request', 'contact_ids': [foreign['id']], 'opportunity_id': row['id']}
    assert post(client, '/campaigns', payload).status_code == 403
    assert post(client, '/campaigns/preview', {'subject': 'Hello', 'body': 'Hello', 'contact_id': foreign['id'], 'opportunity_id': row['id']}).status_code == 403
    payload['contact_ids'] = [contact['id']]
    draft = post(client, '/campaigns', payload).json()
    ceo_cookies = dict(client.cookies)
    client.cookies.clear()
    staff, *_ = authenticate(client, 'new-owner@example.org', 'Staff')
    staff_cookies = dict(client.cookies)
    assert post(client, f'/campaigns/{draft["id"]}/actions', {'action': 'submit', 'version': 1}).status_code == 404
    switch(client, ceo_cookies)
    assert post(client, f'/opportunities/{row["id"]}/assign', {'owner_id': staff, 'version': 1}).status_code == 200
    switch(client, staff_cookies)
    assert client.get(f'/api/campaigns/{draft["id"]}').json()['can_manage']
    assert post(client, f'/campaigns/{draft["id"]}/actions', {'action': 'submit', 'version': 1}).status_code == 200
    switch(client, ceo_cookies)
    assert post(client, f'/campaigns/{draft["id"]}/actions', {'action': 'approve', 'version': 1}).status_code == 200
    switch(client, staff_cookies)
    assert 'campaign.approve' in [n['kind'] for n in client.get('/api/notifications').json()['items']]
