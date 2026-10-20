# Foundation architecture

## Runtime and structure

React 19/TypeScript/Vite, Tailwind 4, shadcn/ui with Radix, React Router, TanStack Query, React Hook Form, and Zod. Inter is self-hosted. The neutral palette and app monogram are application design choices, not claimed official company branding.

FastAPI exposes REST under `/api`. SQLAlchemy 2/psycopg connect to PostgreSQL; Alembic owns schema changes. Vite/Nginx proxy API calls under the frontend origin. `/api/health` checks connectivity and migration readiness.

For local LAN use, the root `npm start` launcher enumerates IPv4 network adapters, prints the interface URLs, and starts Vite on `0.0.0.0:5173` with the API on `127.0.0.1:8000`. `npm run start:preview` serves the built frontend on 4173. Each start combines detected origins with configured origins in the child-process environment, preserving origin/CSRF checks without editing `.env`. LAN HTTP cookies apply only to this development launcher; it refuses production settings. IP changes require a launcher restart. The Windows firewall helper limits frontend access to the local subnet.

Repeated starts reuse an already-running frontend only after verifying its NTECH page, API readiness, and credentialed origin response headers on proxied health requests from the current local/LAN origins. This exits successfully without starting duplicate processes or changing the running API target. Unrelated listeners, unhealthy proxies, and interfaces that cannot serve the LAN origins receive an actionable conflict message.

- `frontend/src/features`: authentication and organization workflows; pages compose shared UI.
- `backend/app/api`: validation and authorization dependencies.
- `backend/app/core`: configuration, session security, hashing, permissions.
- `backend/app/models.py`: initial relational model; split by domain as it grows.
- `backend/app/services`: explicit response serialization, excluding credentials/secrets.
- `backend/alembic`: reproducible schema migrations.
- `deployment`: Ubuntu templates, not installed on a server.

## Data and authorization

Organizations have multiple classifications, many contacts, an owner, and an optional partner profile. Capabilities have a normalized partner association. Initial contacts belong to one organization; shared person affiliations can be added through a later association-table migration. Organization names have Unicode-normalized uniqueness as a conservative initial deduplication policy. Branches sharing a legal name need an expanded identification model. Archived records retain identifiers/history.

Roles, responsibilities, permissions, and assignments are separate tables. CEO covers every declared permission. Manager defaults include operational/finance access, excluding staff/access administration. Staff combine their role and functional permissions. Manager/Staff roles can be configured in Settings. Responsibility permissions are stored separately and visible in Settings; their editing UI is deferred.

Backend checks cover every business operation. `organizations.all` grants company visibility; other permitted staff only access organizations they own. Contacts/history follow the parent scope. Dashboard counts use the same scope and hide staff counts without `staff.read`.

## Security

Argon2id hashes passwords. Random session/CSRF tokens are stored only as hashes. HttpOnly session cookies and checked CSRF headers protect mutations; origins are explicitly allowlisted. Production requires secure cookies and HTTPS. Restricted 10-minute sessions permit MFA enrollment/verification only; business access also requires temporary-password replacement.

TOTP secrets are encrypted using a separately preserved Fernet key. Accepted time counters reject replay. Recovery codes are random, hashed, single-use, and shown once. MFA completion rotates sessions. Password changes revoke other sessions; deactivation revokes all. Database-backed throttling uses advisory locks across API processes.

Authentication, staff, permission, organization, and contact changes create audit records without credentials/secrets. Organization UI shows the latest 30 events; the API supports additional pages. External tamper-resistant audit archival and a global audit viewer are deferred.

## PWA and interface

An explicit Workbox service worker uses Vite PWA injectManifest. Only public build assets are precached. Navigation fallback excludes `/api`; no API runtime cache exists. Query data remains in memory and is cleared on logout/account changes. Offline reload shows a connection error. Installation is browser-aware; updates require an explicit reload after saving work.

Desktop sidebar collapses; mobile uses an accessible drawer. Directory tables become mobile cards. Empty/error/upcoming/loading states reflect actual availability. Global search currently searches organization names; notifications are explicitly upcoming.

## Later increments

Redis/Celery and email integration are not required for this synchronous foundation and are not running. Outreach will add provider adapters, durable database schedules, a single scheduler, controlled retries, suppression, and reply checks. Requirements, eligibility/KNN, commercial finance, delivery, and advanced reports follow later.
