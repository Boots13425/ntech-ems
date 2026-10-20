"""Create a fresh recovery-test database, restore a backup, and compare record counts."""
import os
import subprocess
import sys
from pathlib import Path

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.models import Base


def main():
    source_url = get_settings().database_url.get_secret_value()
    source = make_url(source_url)
    target_name = f"{source.database}_restore_test"
    with psycopg.connect(os.environ.get("ADMIN_DATABASE_URL", "host=127.0.0.1 dbname=postgres user=postgres"), autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_name,)).fetchone():
            raise SystemExit("Recovery-test database exists. Existing data was preserved; use a fresh target for another drill.")
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(target_name), sql.Identifier(source.username)))
    backup_dir = Path(__file__).resolve().parents[2] / "backups"
    subprocess.run([sys.executable, "-m", "app.backup", "backup", "--directory", str(backup_dir)], check=True)
    latest = max(backup_dir.glob("*.dump.enc"), key=lambda p: p.stat().st_mtime)
    environment = os.environ.copy()
    target_url = source.set(database=target_name).render_as_string(hide_password=False)
    environment["RESTORE_DATABASE_URL"] = target_url
    subprocess.run([sys.executable, "-m", "app.backup", "restore", "--file", str(latest), "--confirm-database", target_name], env=environment, check=True)
    original_engine = create_engine(source_url, hide_parameters=True)
    restored_engine = create_engine(target_url, hide_parameters=True)
    with original_engine.connect() as original, restored_engine.connect() as restored:
        assert original.scalar(text("SELECT version_num FROM alembic_version")) == restored.scalar(text("SELECT version_num FROM alembic_version"))
        for table in Base.metadata.sorted_tables:
            query = select(func.count()).select_from(table)
            assert original.scalar(query) == restored.scalar(query), f"Record counts differ for {table.name}"
    original_engine.dispose()
    restored_engine.dispose()
    print(f"Restore drill passed: revision and counts match across {len(Base.metadata.tables)} tables. Recovery database retained for inspection.")


if __name__ == "__main__":
    main()
