# Email configuration

The CEO can open **Settings → Email Configuration** and edit the SMTP host, port,
security mode, sender name/email, username, and password. This prepares the sender
for email features; campaign creation and delivery remain a separate module.

**Save Configuration** stores settings in PostgreSQL. Every test reads the current
database row, so saved changes require no restart. Saving does not contact the SMTP
provider. **Test Connection** checks connection, TLS and authentication without
sending mail. **Send Test Email** submits one fixed message to the entered recipient.
Server acceptance does not guarantee inbox delivery; check spam as well. Tests use
saved settings and are disabled while there are unsaved edits. Requests are limited
to ten tests per CEO per fifteen minutes. Tests are never automatically retried.

Use STARTTLS (typically port 587) or implicit TLS (typically port 465), following
your provider's instructions. Certificates are verified. The None mode supports
unauthenticated relays only; SMTP passwords cannot be sent without TLS. Providers
may require an app password or explicit SMTP authorization. OAuth-only providers
are not supported by this username/password configuration.

Leave the password field blank to preserve the stored password. When changing the
username, supply a new password. To remove authentication, clear the username and
select Clear saved password. Passwords never appear in API responses; the page only
indicates whether one is configured. Both username and password are encrypted at
rest. The username is returned to the authorized CEO for editing.

## Deployment

1. Back up the database and existing encryption keys.
2. Optionally supply a dedicated `SMTP_ENCRYPTION_KEY` in the backend environment
   before the first SMTP save. Generate it with the existing `cryptography` package:
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
   If omitted, the existing `MFA_ENCRYPTION_KEY` is used. Store the effective key
   securely outside database backups. Do not switch keys after saving credentials
   without migrating the ciphertext; restoring a database requires the same key.
3. From `backend`, run `.\.venv\Scripts\python.exe -m alembic upgrade head`
   on Windows, or `.venv/bin/python -m alembic upgrade head` on Linux.
4. Build the frontend with `npm.cmd --prefix frontend run build` from the root.
5. Restart the backend once to load this release and deploy the built frontend.
   Subsequent saves in Settings require no restart. No new dependencies are needed.
6. Sign in as CEO, save the provider details, test the connection, then send a test
   to a mailbox you control. Use HTTPS in production to protect submitted credentials.

Optional `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY`, `SMTP_SENDER_NAME`,
`SMTP_SENDER_EMAIL`, `SMTP_USERNAME`, and `SMTP_PASSWORD` environment values prefill
the initial form. They are used only before a database configuration exists. GET
does not create a row. Once saved, the database is authoritative, including empty
credentials, and the application never rewrites `.env`. Environment changes need
a process restart; routine CEO edits do not.

The migration creates one constrained configuration row. Concurrent edits are
checked against `updated_at`; a stale save returns a conflict and requires reloading.
Audit events record the actor, time, changed field names and test success/failure,
without configuration values, credentials, recipient addresses, or provider responses.

## Verification

Run `python -m pytest -q` using the backend virtual environment, then build the
frontend and run `python scripts/check_e2e.py`. Both use the guarded `_test` database
and must run sequentially. Browser checks use a loopback SMTP sink that never relays
mail, covering save/reload, password redaction, connection testing, and test submission.
API tests cover CEO/MFA/CSRF restrictions, encryption, input validation, stale updates,
immediate changes, TLS modes and redacted errors. A real provider's credentials,
network access, sender authorization and final inbox delivery must be checked using
the settings buttons after configuration.
