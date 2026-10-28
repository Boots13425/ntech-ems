# Implementation status

## Private in-app notifications - 28 October 2026

- Persistent recipient-specific inbox, unread badge/filter, pagination, single/all read actions, and campaign/settings navigation. Refreshes every 15 seconds.
- Submission alerts target active authorized CEO/Manager reviewers; decisions/status changes and replies target the campaign owner. Account/password events target the affected user only.
- Server-enforced recipient isolation and current permissions, transactional inserts, reply deduplication, and no sensitive credential content.
- Migration `0005_notifications` includes pending-approval backfill. See `docs/NOTIFICATIONS.md` for deployment and recipient rules.
- Verified: backend notification/security/campaign regression, TypeScript/production build, and real browser/API/database staff submission -> reviewer alert/approval -> owner alert/read persistence. Reply ingestion creates one owner alert even on replay.


## Email campaigns — 22 October 2026

- Implemented: PostgreSQL campaign/template/recipient/approval/outbound/inbound/suppression/sync records; scoped APIs, strict personalization, approvals, durable sending, threaded follow-ups, IMAP synchronization, manual outcomes and suppression. React overview/editor/templates/details and CEO incoming-mail settings are integrated.
- Modified: campaign models/API/services/worker, automatic API-owned runner (`services/campaign_runtime.py`), migrations `0003_campaigns`/`0004_campaign_runtime`, auth permission refresh, campaign UI health/queue indicators, settings/routes, LAN startup message, browser/test harness and operating guide.
- Delivery repair: API startup now starts the worker automatically; launch/resume wakes it. Added persisted heartbeat and visible processing/mailbox health. Existing approved-but-unlaunched campaigns remain unsent. Pause holds initial emails and follow-ups while reply synchronization continues; resume preserves original due dates.
- Access repair: `campaigns.read` grants company campaign/history viewing. Staff cannot change another employee's campaign; editing and launch remain owner/manager restricted. Browser permissions refresh within 15 seconds. Browser test verifies CEO granting/revoking Staff campaign reading without signing in again.
- Gmail repair: live diagnostics found the actual reply at INBOX UID 7797 behind a scanner stuck at UID 3194. Scanner now uses the campaign date window, batched headers and relevant bodies only, discovers localized Gmail All Mail via `\All`, and excludes own sent messages. Versioned cursor replay safely recovered the existing response without duplicating messages.
- Verified: full backend regression passed 55 tests, then expanded campaign tests passed all 24 (57 distinct tests across runs); production build passed. Full browser regression including Staff grant/read/revoke passed in 49.8 seconds, alongside campaign, settings/local SMTP sink, MFA, organization/contact, mobile and offline flows. Test database records cleaned up. Production/test schemas migrated to `0004_campaign_runtime`.
- Live evidence: EMS restarted at port 5200/API 8100 with automatic worker. Gmail sync caught up (UID 8610 at first verification), error cleared and heartbeat healthy. `Requesting for the partnership` has 1 recorded reply and recipient outcome `replied`; `ANOTHER REQUEST` has no matched reply and retains its scheduled follow-up. Existing outgoing counts remain 2 accepted and 1 queued; no extra test campaign was created or sent.
- Integration limits: IMAP password/app-password authentication; Gmail All Mail and generic-provider INBOX supported. HTML-only content is flagged for mailbox review; attachments are not processed. Actual future follow-up timing is exercised with isolated tests, not by accelerating the user's live schedule.
- Operating guide: `docs/EMAIL_CAMPAIGNS.md`. Normal API startup includes delivery and reply checking. Optional standalone service is for deployments with `CAMPAIGN_WORKER_ENABLED=false` on the API.
- Next: no implementation blocker; normal operation will check new Gmail replies and send eligible scheduled follow-ups automatically while the server runs.

Foundation scope, 20 October 2026. No fabricated business records or default credentials are installed.

## Implemented

- [x] Responsive React/TypeScript/Tailwind/shadcn interface, sidebar/drawer, profile, protected navigation.
- [x] Dashboard, staff, organization/contact management, partner/customer filtered views, security settings.
- [x] Honest upcoming states for opportunities, projects, reports; campaign module added above.
- [x] PWA manifest/icons, public-asset-only worker, offline errors, install/update handling.
- [x] PostgreSQL/Alembic models, real readiness, structured logs, sanitized errors.
- [x] Argon2id, cookie sessions, mandatory TOTP, single-use recovery, CSRF/origins, throttling.
- [x] CEO bootstrap, staff provisioning/deactivation, role/responsibility assignment, temporary-password replacement.
- [x] Backend functional/record permissions, configurable Manager/Staff roles.
- [x] Organization create/view/update/archive, deduplication, search/filter/sort/pagination, contacts/history.
- [x] Database-derived relationship/staff counts and activity.
- [x] Encrypted backups, archive verification, guarded empty-target restore utilities.
- [x] LAN startup for development/build preview, automatic IPv4 discovery, per-run explicit origins, same-origin API proxy, a Windows local-subnet firewall helper, and reuse of verified healthy instances on repeated starts.

## Verification

- [x] Migration applied to application and isolated test databases.
- [x] 14 backend tests passed: auth/MFA/recovery/replay, sessions, CSRF/origins, roles/staff, ownership, organizations/contacts, metrics/audit, throttling, validation redaction.
- [x] TypeScript check and production build including the generated service worker.
- [x] Browser workflow passed: password login, authenticator enrollment/verification, recovery-code acknowledgement, organization/contact creation and edits, partner/customer views, staff/upcoming pages, mobile drawer and no horizontal overflow.
- [x] Manifest/icons/active service worker, no Chromium installability errors, no API responses in Cache Storage, no localStorage credentials, and offline reload/reconnection passed.
- [x] Encrypted backup restored into a separate recovery database; migration revision and record counts matched across all 19 model tables.
- [x] LAN discovery/configuration and existing-instance checks passed (9 tests); backend suite passed again (14 tests), and browser workflows passed on both loopback and the detected LAN IPv4 address, including foreign-origin rejection. Repeated startup from the backend directory was verified against the existing frontend on 5173. Windows frontend firewall rules were installed and verified with local-subnet scope. A second physical device/router path remains to be checked.

Screenshots of desktop/mobile dashboards and organization detail were visually inspected. Verification records were confined to the test database and removed afterwards. The application database contains access configuration only; create the real CEO with the documented bootstrap command.

## Deferred

- Email activation/password-reset links and provider integration; activation is currently administrator controlled, with saved-code MFA recovery.
- Advanced partner intelligence, customer requirements, eligibility/KNN, agreements.
- OAuth-only incoming-mail provider adapters, advanced campaign analytics, distributed high-throughput workers.
- Opportunities/finance, projects/tasks, reports/exports.
- Responsibility-permission editing UI, global audit viewer, archive recovery UI, history UI beyond recent 30 events.
- Ubuntu production/TLS, scheduled/offsite backups, retention, monitoring, production recovery sign-off.
