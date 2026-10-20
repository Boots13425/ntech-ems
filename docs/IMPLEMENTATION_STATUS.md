# Implementation status

Foundation scope, 20 October 2026. No fabricated business records or default credentials are installed.

## Implemented

- [x] Responsive React/TypeScript/Tailwind/shadcn interface, sidebar/drawer, profile, protected navigation.
- [x] Dashboard, staff, organization/contact management, partner/customer filtered views, security settings.
- [x] Honest upcoming states for campaigns, opportunities, projects, reports, notifications.
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
- Campaigns/approvals/follow-ups, email sync, Redis/Celery workers.
- Opportunities/finance, projects/tasks, notifications, reports/exports.
- Responsibility-permission editing UI, global audit viewer, archive recovery UI, history UI beyond recent 30 events.
- Ubuntu production/TLS, scheduled/offsite backups, retention, monitoring, production recovery sign-off.
