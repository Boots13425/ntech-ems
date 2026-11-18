# Opportunities and follow-up work

Opportunities connect a customer requirement to an accountable owner, pipeline
stage, estimated value, expected close date, and next action. The shared logbook and follow-up tasks live here. **Every email and reply stays in Email campaigns.**

## Shared logbook

Open an opportunity and select **Record activity** in its timeline. Record an
initial or follow-up meeting, phone call, proposal, agreement, progress update,
note, or correction. Each entry includes the event date/time, author, details,
optional participants, and outcome or agreement. The recorded timestamp is also
preserved. Future work belongs in tasks rather than a future-dated activity.

Select **Schedule a follow-up from this entry** to save the log and its next task
in one transaction. Ownership comes from the opportunity. Retrying the same save
does not duplicate the entry or task. Existing due-soon and overdue reminders
apply automatically. Closed opportunities accept historical notes but must be
reopened before scheduling new work.

Tasks show **Planned**, **In progress**, or **Completed**. Start, complete, reopen,
and reschedule them as work progresses. The timeline automatically records
creation, assignment, stage/detail changes, and task changes, including old and
new task details. Linked campaign creation/actions, email sending outcomes, and newly received replies
also appear automatically; email bodies remain in Campaigns under its access
rules. Source-conversation replies are logged against their opportunity too.

Timeline entries are preserved: add a correction instead of overwriting history.
The timeline is ordered by event date (newest first), provides separate staff and
automatic filters, loads 30 entries per page, and refreshes every 30 seconds.
Dates are shown in the viewer's local timezone. Existing audit history is migrated
as recorded; missing historical meeting details are not reconstructed.

Migration `0008_opportunity_logbook` adds the timeline table, backfills existing
opportunity audit events, and adds task start timestamps. It preserves existing
accounts, opportunities, tasks, and business records. New automatic campaign
entries are recorded from this update onward.

## Daily flow

1. Create an opportunity from an organization, the Opportunities page, or a launched
   campaign conversation. A conversation can seed one opportunity; subsequent
   visits link to it when the user has access.
2. Staff submit without choosing an owner. Authorized managers and the CEO receive
   an assignment alert, then choose an active owner. They can reassign later.
3. The owner records requirements and moves through New, Qualified, Proposal,
   Negotiation, Won, or Lost. A loss reason is mandatory for Lost.
4. Add follow-up tasks with a due time. Complete, reschedule, or reopen tasks as the
   work progresses. My work today appears on the dashboard and Opportunities page.
5. Use **Compose in Campaigns** to open the existing campaign editor with the
   opportunity company and a recommended contact selected. Compose, preview,
   submit, approve, and launch using the existing campaign flow. This creates a
   linked campaign; it does not bypass approval or send an email from Opportunities.
6. View original and subsequent campaign links from the opportunity. Their email
   content, replies, delivery status, and suppression controls remain in Campaigns.

## Access rules

- `opportunities.read` is the module permission. CEO/Manager roles can oversee all
  opportunities. All users with this permission can view the company opportunity
  list, details, tasks, and timeline. Only management and the assigned owner can
  update an opportunity, record activities, or change tasks.
- Staff can view unassigned submissions but cannot assign themselves,
  assign others, or start task work until management assigns an owner.
- Only a CEO or Manager with module access can assign/reassign. The new owner must
  be active and have Opportunities access. Ownership changes do not transfer the
  organization's general access or change its relationship owner.
- Linked campaign composition allows access only to that opportunity's company
  contacts, independently of general directory ownership. `campaigns.read` is
  still required. New linked drafts retain normal campaign approvals and sending
  restrictions. Original source campaigns retain their existing access rules.
- Assignment changes immediately revoke the old owner's editing access, including
  linked draft editing. Shared read access remains. Private opportunity alerts
  stay recipient-specific and are filtered using current assignment.
- Existing company-wide campaign viewing is unchanged.
- Duplicate conversation conversion, stale edits, negative values, invalid dates,
  foreign contacts, unauthorized assignment, and cross-opportunity task edits are
  rejected by the API. Assignment/stage/task actions are audited.

## Work and management views

- My work today lists up to 100 oldest open tasks due before the next midnight in
  Africa/Douala, including overdue work. The owner is inherited from the opportunity.
- Pipeline filters include stage, assigned to me, awaiting assignment, no next
  action, and overdue follow-ups. Managers can expand team progress by owner.
- Estimated open pipeline values are totaled separately for XAF, USD, EUR and GBP.
  They are estimates, not revenue or currency-converted forecasts.
- Tasks on Won/Lost opportunities remain in history but leave today's work and stop
  reminders. Reopen the opportunity to start new work.
- The existing automatic worker emits one due-soon reminder within 24 hours of a
  deadline and one overdue reminder. Completing a task stops reminders. Rescheduling
  or reassigning resets reminder eligibility. No SMTP setup is needed for in-app
  reminders, but the API worker (or standalone campaign worker) must be running.
- Assigned owners receive relevant linked-campaign decisions and replies. Source
  conversation replies additionally notify the opportunity owner without duplicating
  alerts when they already own the campaign.

## Deployment

Migration `0006_opportunities` introduced opportunity/task/source tables and the optional
campaign association. It adds the existing `opportunities.read` permission to the
Staff role. Existing business data is
preserved and no sample opportunities or emails are created.

From the repository root:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
Pop-Location
npm.cmd --prefix frontend run build
```

Restart each existing EMS launcher with its original frontend/API ports and reload
the browser. A frontend refresh alone cannot update Python endpoints.

Verification uses the guarded test database: run backend pytest and
`backend/scripts/check_e2e.py` sequentially. The browser checks staff creation,
management assignment, task completion, mobile layout, and linked composition
through Campaigns without sending email to a real customer.
