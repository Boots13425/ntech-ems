"""Encrypted local backups. Restore only into an explicitly named empty database."""
import argparse
import hashlib
import hmac
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def encryption():
    key = os.environ.get("BACKUP_ENCRYPTION_KEY")
    if not key:
        # Settings loads the same ignored env file; dotenv avoids exposing secret values to argv.
        from dotenv import dotenv_values
        key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("BACKUP_ENCRYPTION_KEY")
    if not key:
        raise SystemExit("Set a separate BACKUP_ENCRYPTION_KEY. Store it securely outside the backup directory.")
    return Fernet(key.encode())


def connection_environment(url):
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise SystemExit("PostgreSQL is required")
    environment = os.environ.copy()
    environment.update(PGHOST=parsed.host or "127.0.0.1", PGPORT=str(parsed.port or 5432), PGUSER=parsed.username or "", PGPASSWORD=parsed.password or "", PGDATABASE=parsed.database or "")
    return environment


def run(program, args, environment):
    if not shutil.which(program):
        raise SystemExit(f"{program} must be available on PATH")
    result = subprocess.run([program, *args], env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        # Do not echo a database DSN or process environment when a tool fails.
        raise SystemExit(f"{program} failed (exit {result.returncode}). Check database access and tool/server versions.")


def verified_plaintext(path, target):
    encrypted = path.read_bytes()
    checksum = path.with_suffix(path.suffix + ".sha256")
    if not checksum.exists() or not hmac.compare_digest(hashlib.sha256(encrypted).hexdigest(), checksum.read_text().strip()):
        raise SystemExit("Backup checksum validation failed")
    try:
        target.write_bytes(encryption().decrypt(encrypted))
    except InvalidToken:
        raise SystemExit("Backup authentication failed: wrong encryption key or damaged backup") from None
    run("pg_restore", ["--list", str(target)], os.environ.copy())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backup", "verify", "restore"])
    parser.add_argument("--directory", type=Path, default=Path("../backups"))
    parser.add_argument("--file", type=Path)
    parser.add_argument("--confirm-database")
    args = parser.parse_args()
    settings = get_settings()
    source_url = settings.database_url.get_secret_value()
    with tempfile.TemporaryDirectory(prefix="ntech-backup-") as temporary:
        os.chmod(temporary, 0o700)
        plain = Path(temporary) / "database.dump"
        if args.command == "backup":
            encryption()  # Fail before creating a plaintext dump if the key is missing.
            args.directory.mkdir(parents=True, exist_ok=True)
            os.chmod(args.directory, 0o700)
            run("pg_dump", ["--format=custom", "--no-owner", "--no-privileges", "--file", str(plain)], connection_environment(source_url))
            output = args.directory / f"ntech-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.dump.enc"
            encrypted = encryption().encrypt(plain.read_bytes())
            output.write_bytes(encrypted)
            os.chmod(output, 0o600)
            output.with_suffix(output.suffix + ".sha256").write_text(hashlib.sha256(encrypted).hexdigest(), encoding="ascii")
            verified_plaintext(output, plain)
            print(f"Encrypted backup created and archive verified: {output}")
        else:
            if not args.file:
                parser.error("--file is required")
            verified_plaintext(args.file, plain)
            if args.command == "verify":
                print("Checksum, encryption authentication, and PostgreSQL archive structure verified. A restore drill is still required to prove recovery.")
                return
            target_url = os.environ.get("RESTORE_DATABASE_URL", "")
            if not target_url:
                parser.error("Set RESTORE_DATABASE_URL to a separate, empty PostgreSQL database")
            source, target = make_url(source_url), make_url(target_url)
            if (source.host, source.port, source.database) == (target.host, target.port, target.database):
                parser.error("Restore into the source database is forbidden")
            if not args.confirm_database or args.confirm_database != target.database:
                parser.error("--confirm-database must match the target database name")
            environment = connection_environment(target_url)
            with psycopg.connect(host=environment["PGHOST"], port=environment["PGPORT"], user=environment["PGUSER"], password=environment["PGPASSWORD"], dbname=environment["PGDATABASE"]) as connection:
                if connection.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'").fetchone()[0]:
                    parser.error("The restoration target must be empty; no existing tables were changed")
            run("pg_restore", ["--exit-on-error", "--no-owner", "--no-privileges", "--dbname", target.database, str(plain)], environment)
            print("Backup restored successfully. Validate record counts and sign-in against the restored database before declaring recovery complete.")


if __name__ == "__main__":
    main()
