"""Run real browser verification against a disposable, guarded PostgreSQL test database."""
import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
from app.core.config import Settings
from smtp_test_server import smtp_sink


def wait_ready(url, process):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Verification server exited before becoming ready")
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError):
            time.sleep(.25)
    raise RuntimeError("Verification server readiness timed out")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lan', action='store_true', help='Exercise the LAN launcher and detected network address')
    args = parser.parse_args()
    base_url = 'http://127.0.0.1:4173'
    if args.lan:
        addresses = json.loads(subprocess.check_output(['node', str(root / 'scripts/lan.mjs')], text=True))
        if not addresses:
            raise SystemExit('No LAN IPv4 address found; connect to Wi-Fi/Ethernet before the LAN check')
        base_url = f"http://{addresses[0]['address']}:4173"
    print(f'Browser verification: {base_url}', flush=True)
    config = Settings()
    url = config.test_database_url.get_secret_value() if config.test_database_url else ""
    if not url or not make_url(url).database.endswith("_test") or url == config.database_url.get_secret_value():
        raise SystemExit("A separate TEST_DATABASE_URL ending in _test is required")
    os.environ["DATABASE_URL"] = url
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.core.permissions import seed_access
    from app.core.security import hash_password
    from app.db.session import SessionLocal, engine
    from app.models import Base, Role, User
    from sqlalchemy import select
    command.upgrade(Config(str(root / "backend/alembic.ini")), "head")

    def clean():
        with engine.begin() as connection:
            names = ', '.join('"' + table.name + '"' for table in Base.metadata.sorted_tables)
            connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))

    clean()
    password = secrets.token_urlsafe(30)
    email = f"browser-{secrets.token_hex(6)}@example.org"
    staff_password = secrets.token_urlsafe(30)
    staff_email = f"browser-staff-{secrets.token_hex(6)}@example.org"
    with SessionLocal() as db:
        seed_access(db)
        db.add(User(full_name="Workspace Verification", email=email, password_hash=hash_password(password), roles=[db.scalar(select(Role).where(Role.name == "CEO"))]))
        staff_role = db.scalar(select(Role).where(Role.name == 'Staff'))
        staff_role.permissions = [p for p in staff_role.permissions if p.code != 'campaigns.read']
        db.add(User(full_name='Staff Verification', email=staff_email, password_hash=hash_password(staff_password), roles=[staff_role]))
        db.commit()
    environment = os.environ.copy()
    environment.update(E2E_EMAIL=email, E2E_PASSWORD=password, COOKIE_SECURE="false", API_PROXY_TARGET="http://127.0.0.1:8001", E2E_BASE_URL=base_url, CAMPAIGN_WORKER_ENABLED="false")
    environment.update(E2E_STAFF_EMAIL=staff_email, E2E_STAFF_PASSWORD=staff_password)
    log_dir = root / ".verification"
    log_dir.mkdir(exist_ok=True)
    processes = []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        with (log_dir / "api.log").open("w") as api_log, (log_dir / "frontend.log").open("w") as frontend_log:
            if args.lan:
                launcher = subprocess.Popen(['node', str(root / 'scripts/start-lan.mjs'), '--preview', '--api-port', '8001'], cwd=root, env=environment, stdout=api_log, stderr=api_log, creationflags=flags)
                processes.append(launcher)
                wait_ready(base_url + '/api/health', launcher)
            else:
                api_process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"], cwd=root / "backend", env=environment, stdout=api_log, stderr=api_log, creationflags=flags)
                processes.append(api_process)
                wait_ready("http://127.0.0.1:8001/api/health", api_process)
                frontend = subprocess.Popen(["node", str(root / "frontend/node_modules/vite/bin/vite.js"), "preview", "--host", "127.0.0.1", "--port", "4173", "--strictPort"], cwd=root / "frontend", env=environment, stdout=frontend_log, stderr=frontend_log, creationflags=flags)
                processes.append(frontend)
                wait_ready(base_url, frontend)
            with smtp_sink() as smtp:
                environment["E2E_SMTP_PORT"] = str(smtp.server_address[1])
                result = subprocess.run(["node", str(root / "frontend/node_modules/@playwright/test/cli.js"), "test", "--reporter=line"], cwd=root / "frontend", env=environment)
                if result.returncode == 0 and not any(b"NTECH EMS test email" in message for message in smtp.messages):
                    raise RuntimeError("Browser email test did not reach the local SMTP sink")
                return result.returncode
    finally:
        try:
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name == 'nt' and args.lan:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL, check=True)
                    else:
                        process.terminate()
                    process.wait(timeout=10)
        finally:
            try:
                clean()
            finally:
                engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
