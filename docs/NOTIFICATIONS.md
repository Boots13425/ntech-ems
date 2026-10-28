# In-app notifications

Notifications are private database records, addressed to a specific user. The bell
refreshes every 15 seconds and when the browser regains focus. Open it to view
history, filter unread items, mark one/all as read, or open the relevant campaign
or account settings. Read state survives reloads and sign-ins.

## Recipient rules

| Event | Recipients |
| --- | --- |
| Campaign submitted | Active CEOs/Managers with `campaigns.read`, excluding the submitting actor |
| Campaign approved/rejected, launched, paused, resumed, cancelled, edited, or submitted by someone else | Campaign owner, excluding the acting user |
| New matched campaign response | Campaign owner only; duplicate ingestion does not create another alert |
| Staff account created or its details/access changed | Affected active account only |
| Role permissions changed | Active members of that role only |
| Password changed | Account whose password changed only |
| CEO resets a password | Affected staff account only |

Approval/rejection notes remain in the campaign's approval history; the alert links
there. Notifications never contain passwords, MFA secrets, email bodies, or
credentials. This feature adds no browser push notifications or notification emails.
The CEO can reset an active team member's password from Staff management using
the Reset password button beside Edit. Creation and reset share the same server
generator and copy dialog. Reset replaces the password hash, revokes all sessions,
and requires a password change at next sign-in. Existing MFA stays enabled. The
temporary password is returned only in the reset response; it is never placed in
notifications or audit logs. A CEO changes their own password in account settings.
This feature requires a backend restart and frontend rebuild, with no additional
database migration beyond the existing notification schema.

## Enforcement

- The authenticated session determines the recipient for every list/count/read
  request. Clients cannot select another user's inbox or create arbitrary alerts.
- Authentication, completed MFA/password setup, account activation, and CSRF checks
  apply. Unknown or other-user notification IDs return 404 for read operations.
- Campaign notifications require current `campaigns.read` access; reviewer alerts
  also require a current CEO/Manager role. Losing access hides those alerts and
  removes them from unread counts. Campaign endpoints independently enforce access.
- Event changes and notification inserts commit in the same transaction.
- No-op staff edits and failed/repeated campaign transitions do not produce alerts.
- API responses are `no-store`; only public assets are stored by the service worker.
- Existing company-wide campaign viewing permissions are unchanged. Private inboxes
  do not change who is authorized to view a campaign itself.

## Update an existing installation

From the repository root, using the existing backend environment:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m alembic upgrade head
Pop-Location
npm.cmd --prefix frontend run build
```

Restart the existing API/preview process using its normal launcher, then reload
the frontend. Migration `0005_notifications` adds the table/indexes and alerts
eligible reviewers about campaigns already pending approval. It does not send
emails or alter campaign approval/sending states. Historical account events are
not reconstructed. Keep the migration, backend, and frontend changes together.

## Verification

Run suites sequentially because they share the guarded test database:

```powershell
Push-Location backend
.\.venv\Scripts\python.exe -m pytest tests/test_notifications.py tests/test_foundation.py tests/test_campaigns.py -q
.\.venv\Scripts\python.exe scripts/check_e2e.py
Pop-Location
```

The browser harness uses disposable accounts and the test database. It covers staff
submission, reviewer notification navigation and approval, owner notification,
mark-all-read, and persisted history after reload.

## Missing alerts after an update

A frontend update does not reload an already-running Python backend. Check
`/api/health` and `/api/notifications` through the same frontend URL the user opens.
An unauthenticated notification request should return 401, not 404. A 404 means
that instance does not have the notification routes loaded; restart its existing
launcher with the same frontend/API ports. Multiple LAN launchers can otherwise
serve different backend versions against the same database.

The bell displays an unavailable indicator if polling fails instead of silently
showing no unread alerts. Opening it shows the error and a retry button.

For an incident where an old process recorded campaign events but missed alerts,
`backend/scripts/recover_campaign_notifications.py` reuses the recipient rules to
recover submission/approval/rejection alerts within an explicit timezone-aware
`--since`/`--until` interval. It previews by default; `--apply` commits. Existing
recipient/kind/campaign alerts are preserved, so rerunning is safe. It restores
at most one alert per recipient/kind/campaign, not a full historical event stream.
Campaign states and email delivery are unchanged.

On 28 October 2026 the old 5200/8100 instance had no notification routes while
5202/8102 had the updated routes. The 5200 instance was restarted using its existing
ports; four missing alerts were recovered (two CEO submissions, two owner approvals).
