# Cloud VM dependency and deployment review

Reviewed 9 November 2026 against the repository manifests, application imports, migrations, workers, backup implementation, and deployment templates. This is a source/configuration assessment, not a completed cloud deployment, load test, or full security audit. No production credentials were read.

## Deployment model

Use a Linux VM with systemd, Nginx serving `frontend/dist`, and Uvicorn running the FastAPI backend on loopback port 8000. PostgreSQL can run on the same VM or as a managed private database. The supplied deployment templates target Ubuntu. The commands below assume Ubuntu 24.04 LTS with Python 3.12; adapt package names if choosing another distribution.

The API starts campaign delivery, incoming-mail synchronization, opportunity reminders, and backup scheduling itself. Redis, RabbitMQ, Celery, Docker, PM2, Gunicorn, a local mail server, and a separate cron scheduler are not application requirements. Node is needed where the frontend is built, not to serve its compiled files.

## VM packages

| Package/component | Requirement and purpose |
| --- | --- |
| `python3`, `python3-venv`, `python3-pip` | Python 3.12 or later, isolated backend environment, package installation. Python 3.12 is the conservative baseline for this Ubuntu target. |
| `nginx` | HTTPS termination, static frontend hosting, `/api/` reverse proxy. |
| PostgreSQL server | Required somewhere; install `postgresql` only if hosting the database on this VM. No extra PostgreSQL extension was found in the migrations. |
| `postgresql-client` or version-specific client package | Required on the API VM even with a managed database: provides `pg_dump`, `pg_restore`, and `psql`. Select the server's major version for dump/restore tooling. |
| `ca-certificates`, `openssl` | Trusted certificates for database/mail/download TLS and certificate diagnostics. |
| `tzdata` | Timezone database, including Africa/Douala for schedules. |
| systemd and time synchronization | Normally supplied by Ubuntu; service restart/boot startup and accurate time for MFA and scheduled work. Keep time synchronization enabled. |
| Node.js 24 and bundled npm | Project-documented build target. Required only on VM if building there; otherwise install on CI/build host. Do not assume Ubuntu's default `nodejs` package meets this target. |
| `certbot`, `python3-certbot-nginx` | Conditional: certificate issuance/renewal when using Let's Encrypt directly on the VM. An upstream managed TLS endpoint can replace this arrangement. |
| `git`, `curl` | Deployment/diagnostic conveniences; Git is unnecessary if uploading release artifacts. |
| `ufw` | Optional host firewall, alongside cloud firewall/security-group rules. |

Base package commands for the stated Ubuntu target:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip nginx \
  ca-certificates openssl tzdata git curl
```

For a database hosted on the same VM:

```bash
sudo apt-get install -y postgresql postgresql-client
```

For a managed database, install only its compatible PostgreSQL client package on the API VM. Obtain an appropriate version from PostgreSQL's Ubuntu repository if the distribution version differs. Do not blindly use a default client older than the server.

For VM-managed Let's Encrypt certificates:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
```

Install Node 24 using your approved Node distribution method and verify `node --version` and `npm --version` before building. The Vite 7 baseline is Node 20.19+ or 22.12+; the repository selects Node 24. [Vite 7 requirements](https://v7.vite.dev/guide/migration)

Native compiler toolchains are not baseline requirements when compatible binary wheels are available. `psycopg[binary]` bundles its client libraries. If target architecture/Python lacks wheels, assess `build-essential`, Python development headers, `libffi-dev`, `libssl-dev`, and Rust/Cargo for the affected packages; `libpq-dev` is needed if switching to a source-built Psycopg C installation. Prefer validating binary availability before adding these. [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html)

## Backend Python packages

The complete checked-in pinned package inventory is [requirements.lock](../backend/requirements.lock). Install it rather than manually installing only the direct dependencies below. It also currently includes test tooling, and is not a minimal runtime-only lock.

| Direct dependency from pyproject.toml | Declared range | Purpose |
| --- | --- | --- |
| fastapi | >=0.115,<1 | HTTP API |
| uvicorn[standard] | >=0.34,<1 | ASGI server and supporting extras |
| SQLAlchemy | >=2.0.36,<2.1 | Database access |
| alembic | >=1.14,<2 | Schema migrations |
| psycopg[binary] | >=3.2,<4 | PostgreSQL driver |
| pydantic-settings | >=2.7,<3 | Environment configuration |
| argon2-cffi | >=23.1,<26 | Password hashing |
| pyotp | >=2.9,<3 | MFA |
| cryptography | >=44,<49 | Encryption |
| email-validator | >=2.2,<3 | Email validation |
| setuptools | >=75 | Build/install backend |

Optional test dependencies: `pytest>=8,<10`, `httpx>=0.28,<1`. Transitive packages such as Pydantic, Starlette, python-dotenv, CFFI, and DNS support are recorded in the lock. SMTP, IMAP, threading, and icon generation use Python's standard library; do not install separate packages named `smtplib`, `imaplib`, or Pillow.

Run as the deployment account, with the checkout available at the intended path:

```bash
cd /srv/ntech-ems/backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m pip check
```

The last install builds the application using setuptools. A non-editable installation is shown for releases; the existing deployment document uses editable installation. Neither approach removes the need to reinstall/redeploy after changing code.

Linux portability must be checked before deployment: the lock is a flat pinned list and omits Linux-specific Uvicorn extras such as uvloop. A `--no-deps` install will not resolve platform differences. Validate the complete installation against `uvicorn[standard]` on the target Linux/Python version and produce a tested Linux lock if dependencies differ. Do not treat the existing Windows environment as proof that all pinned packages can be installed on Linux.

## Frontend packages

Install all dependencies, including development dependencies, on the build host. TypeScript, Vite, and Tailwind are necessary to build the production artifact despite their `devDependencies` classification.

Application dependencies from [package.json](../frontend/package.json):

```text
@fontsource-variable/inter  ^5.2.0
@hookform/resolvers         ^5.1.0
@tanstack/react-query       ^5.80.0
class-variance-authority    ^0.7.1
clsx                       ^2.1.1
lucide-react               ^0.468.0
qrcode.react               ^4.2.0
radix-ui                   ^1.8.1
react                      ^19.1.0
react-dom                  ^19.1.0
react-hook-form            ^7.57.0
react-router-dom           ^7.6.0
sonner                     ^2.0.0
tailwind-merge             ^3.3.0
workbox-core               ^7.4.1
workbox-precaching         ^7.4.1
workbox-routing            ^7.4.1
zod                        ^4.0.0
```

Build/test dependencies:

```text
@playwright/test           ^1.56.0
@tailwindcss/vite          ^4.1.0
@types/node               ^22.15.0
@types/react              ^19.1.0
@types/react-dom          ^19.1.0
@vitejs/plugin-react      ^5.0.0
tailwindcss               ^4.1.0
typescript                ~5.9.2
vite                      ^7.3.0
vite-plugin-pwa           ^1.2.0
```

The complete resolved direct and transitive inventory is [package-lock.json](../frontend/package-lock.json). Use:

```bash
cd /srv/ntech-ems/frontend
npm ci --include=dev
npm run build
```

Only `frontend/dist` needs to be served by Nginx. Do not copy Windows `node_modules` or a Windows Python virtual environment to Linux. If browser tests run on the VM, additionally run `npx playwright install --with-deps chromium` on the test host; browser binaries and their system libraries are not normal production runtime requirements. Root `package.json` has no package dependencies and its LAN launcher is not the production service.

## Required configuration and external services

- Domain/DNS, HTTPS certificate, and renewal. Configure Nginx's domain, certificate paths, and static root.
- PostgreSQL database, restricted application credentials, and migration access. Use `DATABASE_URL=postgresql+psycopg://...`. Preserve existing data through a verified migration/restore if this deployment replaces the local system.
- Protected `/etc/ntech-ems/backend.env`: `APP_ENV=production`, `COOKIE_SECURE=true`, `PUBLIC_URL=https://YOUR_DOMAIN`, `ALLOWED_ORIGINS=["https://YOUR_DOMAIN"]`, database URL, `MFA_ENCRYPTION_KEY`, `BACKUP_ENCRYPTION_KEY`, and the effective `SMTP_ENCRYPTION_KEY`. When migrating existing data, retain its existing keys; new keys cannot decrypt the old data.
- `CAMPAIGN_WORKER_ENABLED=true` and `BACKUP_WORKER_ENABLED=true` for the default API-owned workers.
- Private writable `BACKUP_DIRECTORY`, sufficient space for eight retained encrypted backups plus temporary files, and an offsite copy destination. Encryption currently uses memory proportional to the dump size, so capacity must be measured against real database sizes.
- SMTP provider and IMAP mailbox configured through the CEO settings. Allow outbound provider ports, typically SMTP 587/465 and IMAP 993. Verify provider/cloud egress restrictions and actual delivery/reply synchronization.
- Public inbound 443 and 80 for HTTP redirect/certificate validation; restricted administrative SSH. Keep API 8000 and database 5432 private. Development ports 5173/4173/8100 need no public exposure.
- Working DNS, HTTPS access during dependency installation, and time synchronization. Protect secrets and recovery codes separately from the web root and deployment artifacts.

## Findings to resolve before going live

1. **Backup writes are blocked by the supplied service template.** `deployment/ntech-api.service` sets `ProtectSystem=strict` without a writable backup exception. Set `BACKUP_DIRECTORY=/var/lib/ntech-ems/backups` in the environment file and add the following to the unit's `[Service]` section (or a systemd override):

   ```ini
   StateDirectory=ntech-ems
   StateDirectoryMode=0700
   ReadWritePaths=/var/lib/ntech-ems
   ```

   systemd creates the private state directory for the service account. Reload/restart the service and verify a real manual backup under the service account. These changes are recommendations in this report; the service file has not been edited.

2. **Choose one campaign-worker arrangement.** The API already launches it. Leave `ntech-campaign-worker.service` disabled for this model. If deliberately using that separate service, disable the API-owned campaign worker. Keep one API process initially; scaling requires separate capacity and lifecycle validation.
3. **Managed-database TLS needs explicit backup verification.** `backup.connection_environment()` copies host/port/user/password/database into libpq environment variables but does not propagate URL query parameters such as `sslmode` and certificate options. Configure matching `PGSSLMODE`/`PGSSLROOTCERT` as required by the provider and verify both API connectivity and dump/restore connectivity.
4. **Provisioning is incomplete.** Existing templates do not provision DNS, certificates, firewall rules, offsite replication, or external backup-failure alerts. Installing packages alone does not implement these operations.
5. **Apply migrations and initialize access.** With production configuration securely loaded, run `.venv/bin/alembic upgrade head` and `.venv/bin/python -m app.cli seed-access`. Bootstrap the CEO interactively only for a fresh database. Current readiness expects migration `0007_backups`.
6. **Validate package resolution on Linux.** Existing locks document intended versions but this review did not install them on a Linux VM, check every artifact's availability, or run a vulnerability audit. Run `pip check`, frontend typecheck/build, targeted backend tests against an isolated test database, and dependency vulnerability checks before accepting the release.
7. **Complete production acceptance.** Check `nginx -t`, HTTPS `/api/health`, MFA/login, role boundaries, organization/opportunity changes, notifications, SMTP sending, IMAP replies, campaign processing, backup creation/download, restore to a separate database, service restart, and VM reboot. Never run reset-capable test scripts against the production database.

PostgreSQL documents that pg_dump refuses to dump a server newer than its own major version. Match backup tools to the database and verify a real restore, not only archive listing. [PostgreSQL pg_dump documentation](https://www.postgresql.org/docs/current/app-pgdump.html)

The remaining deployment choices are the VM operating system/provider, whether PostgreSQL is local or managed, the domain, and the build location. The package inventory above covers the current application; these choices determine the final installation commands and network configuration.
