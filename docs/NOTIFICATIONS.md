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

Approval/rejection notes remain in the campaign's approval history; the alert links
there. Notifications never contain passwords, MFA secrets, email bodies, or
credentials. This feature adds no browser push notifications or notification emails.
There is no CEO password-reset endpoint in the current application; any future
reset flow must address the affected account through the same notification service.

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
