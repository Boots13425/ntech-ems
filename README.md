# NTECH EMS

ETS-NTECH's internal enterprise workspace. Foundation: React PWA, FastAPI, PostgreSQL, mandatory authenticator MFA, staff access management, organization/contact management, and real-data relationship metrics.

## Local setup (Windows PowerShell)

Requires Node **24 LTS recommended**, Python 3.12+, PostgreSQL, and PostgreSQL client tools on PATH. The installed Node 23 built successfully but is end-of-life.

First-time dependency installation, from the repository root:

```powershell
python -m venv backend/.venv
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

Configure `backend/.env` from `.env.example`, or create new local databases with:

```powershell
.\.venv\Scripts\python.exe scripts/setup_local.py
```

The helper uses local PostgreSQL administrator access through libpq or `ADMIN_DATABASE_URL`. If no password is available, it prompts privately for your local PostgreSQL administrator password. It creates a restricted application role, separate application/test databases, and random local secrets. Existing configuration/database names are preserved. Run this setup on each new workstation. Never commit `.env`.

Apply migrations and bootstrap the first real CEO account:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.cli seed-access
.\.venv\Scripts\python.exe -m app.cli bootstrap-ceo
```

Bootstrap prompts privately for a password; there are no default credentials. At first sign-in, scan the authenticator QR code, verify the code, and save the recovery codes. Staff accounts are provisioned by an authorized administrator; members enroll MFA and replace their temporary password.

## Start the application

From the repository root, start both the API and interface for devices on the same LAN:

```powershell
npm.cmd start
```

The launcher automatically detects this computer's active IPv4 addresses and prints a URL for each network adapter, for example `http://192.168.1.20:5173`. On another device connected to the same network, open the URL beside the server's Wi-Fi/Ethernet adapter. Virtual-machine/VPN adapters may also appear; use the adapter connected to your other devices. Keep the terminal open; **Ctrl+C stops both servers**.

The frontend listens on all IPv4 interfaces. API requests use the same address as the page through Vite's `/api` proxy, while the API and PostgreSQL stay on loopback. The detected addresses are added to the API's explicit origin allowlist for this run; no IP address needs to be entered in `.env` or frontend source. Every start redetects the addresses, so restart the command after changing networks or receiving a new IP. `npm.cmd run lan:urls` lists the current addresses without starting servers.

If NTECH EMS is already running on the frontend port, the launcher checks the interface, API readiness, LAN reachability, and allowed origins, then reports that the existing instance is ready and exits successfully. Keep the original server terminal open. `--api-port` selects the backend port only for a new instance; changing it does not reconfigure an existing frontend. To change the running API port, stop the original launcher with Ctrl+C, then start it again with the new option. An unrelated application or an unhealthy/loopback-only frontend is not reused; the message explains how to stop your frontend or select another port. These commands work from the repository root or the `backend` directory.

On Windows, allow the frontend through the firewall once. Open **PowerShell as Administrator**, change to this repository, and run:

```powershell
.\deployment\enable-lan-firewall.ps1
```

The helper allows Node's TCP ports 5173 and 4173 from the local subnet across Windows network profiles, including networks classified Public. It leaves the API/database ports closed. If PowerShell blocks local scripts, run `powershell.exe -ExecutionPolicy Bypass -File .\deployment\enable-lan-firewall.ps1` in that administrator terminal. For custom ports, pass `-Ports 5200`. Undo the default rules with `Remove-NetFirewallRule -Name NTECH-EMS-LAN-5173,NTECH-EMS-LAN-4173`.

If another device cannot connect, check that both devices share the same network, use the physical adapter's URL, and ensure the router's guest/client isolation is disabled. Do not forward these development ports on your router. The server computer must remain awake.

This launcher is for **development on a trusted LAN** and refuses production configuration. It enables HTTP cookies only in its child processes; it does not change `backend/.env`. LAN HTTP traffic is unencrypted. Use the [HTTPS deployment](docs/DEPLOYMENT.md) for production; service workers and PWA installation require HTTPS outside loopback.

To choose different ports:

```powershell
npm.cmd start -- --port 5200 --api-port 8100
```

### Separate terminals on this computer only

For loopback-only development, the existing separate-terminal commands remain available.

Terminal 1, from the repository root:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2, from the repository root:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open **http://127.0.0.1:5173**. API readiness: **http://127.0.0.1:8000/api/health**. Development API docs: `/api/docs`. Use one hostname consistently for cookies.

## PWA production preview

Build once, then start the API and built frontend together with LAN access, from the repository root:

```powershell
npm.cmd --prefix frontend run build
npm.cmd run start:preview
```

The detected LAN URLs use port **4173**. This is a local build preview, not a production web server. For loopback-only preview with a separately running API, from `frontend`:

```powershell
npm.cmd run build
npm.cmd run preview
```

Open **http://127.0.0.1:4173**. Service workers run in production builds/preview. Installation is offered where supported; some browsers expose their own Add to Home Screen action. HTTPS is required outside loopback. Only public build assets are cached. API responses and business records are not persisted offline. Updates require an explicit reload.

## Verification

From `backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/check_e2e.py
.\.venv\Scripts\python.exe scripts/check_e2e.py --lan
.\.venv\Scripts\python.exe scripts/check_restore.py
```

Run these suites sequentially: backend and browser tests both reset the guarded test database. Browser checks require a frontend build and Playwright Chromium (`npx.cmd playwright install chromium` from `frontend` if missing). They start temporary servers on 8001/4173, use random test-only credentials in memory, exercise the real UI/API/database, and clear test records afterwards. Tests require a separate database ending in `_test`; screenshots/logs go to ignored `.verification/`.

The `--lan` browser check starts the LAN launcher and verifies login/MFA, cookies, rejected foreign origins, organization/contact operations, and mobile navigation through the detected LAN address. PWA/offline checks run only in secure browser contexts; the normal loopback suite continues to cover them. Run `npm.cmd run test:lan` from the root for IP discovery and launch-configuration checks. A request from a second physical device is still needed to verify the router/firewall path.

The restore drill creates a fresh recovery database and compares its migration revision and table counts. It retains that target for inspection and refuses to overwrite it on subsequent runs.

- [Architecture and security](docs/ARCHITECTURE.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md)
- [Backup and recovery](docs/BACKUP_RECOVERY.md)
- [Ubuntu deployment](docs/DEPLOYMENT.md)
- [CEO email configuration](docs/EMAIL_CONFIGURATION.md)
- [Private in-app notifications](docs/NOTIFICATIONS.md)
- [Opportunities and follow-up tasks](docs/OPPORTUNITIES.md)

Matching, projects, and reports have explicit upcoming states. Campaigns, opportunities with follow-up tasks, and private in-app notifications are implemented. Partners/customers are filtered views of real organizations. No demo fixtures enter the application database.
