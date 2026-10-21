# Ubuntu deployment template

For access from devices on the same LAN during development, use `npm.cmd start` from the repository root on Windows (or `npm start` on Linux/macOS). It detects local IPv4 addresses and prints the URLs to share; see [LAN startup and Windows firewall setup](../README.md#start-the-application). This HTTP development mode does not replace the production HTTPS setup below.

Not yet deployed or verified on an Ubuntu server. Requires a domain, server access, TLS, production PostgreSQL credentials, secret keys, and backup destination.

1. Install Ubuntu, Nginx, PostgreSQL, Python 3.12+, and Node 24 LTS. Use a dedicated unprivileged `ntech` account and `/srv/ntech-ems` checkout.
2. Provision a restricted database role/database. Require SCRAM authentication and restrict network access. Use a separately privileged migration role when tightening production access.
3. Create `backend/.venv`, install `requirements.lock`, and install the project with `pip install --no-deps -e .`.
4. Store protected runtime configuration in `/etc/ntech-ems/backend.env`. Set `APP_ENV=production`, `COOKIE_SECURE=true`, `PUBLIC_URL=https://YOUR_DOMAIN`, and `ALLOWED_ORIGINS=["https://YOUR_DOMAIN"]`. Supply the database URL and independent encryption keys.
5. Load configuration securely for administrative commands, apply Alembic migrations, seed access configuration, and bootstrap the CEO interactively. Keep secrets out of arguments/source control.
6. Build `frontend` with `npm ci` and `npm run build`. Give Nginx read access to `frontend/dist` only.
7. Adapt the Nginx template domain/certificates and systemd unit. Run `nginx -t`, enable/start the API service, and reload Nginx. Bind API port 8000 to loopback; only Nginx is a trusted forwarded-header source.
8. Verify HTTPS, readiness, MFA, permission boundaries, real organization/contact changes, mobile layout, installability, updates, and backup recovery on the actual server.

Worker services, certificate issuance, firewall provisioning, automatic deployment, and scheduled/offsite backups are not performed by these templates.

For SMTP setup, encryption-key handling, and the email configuration migration, see
[Email Configuration](EMAIL_CONFIGURATION.md). Deploying this feature requires one
backend restart; subsequent CEO configuration saves apply immediately.
