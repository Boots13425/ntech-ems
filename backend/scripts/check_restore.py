"""Create a fresh recovery-test database, restore a backup, and compare record counts."""
import os
import argparse
import re
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.models import Base
from app.backup import create_backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-database', help='Fresh recovery database name ending in _restore_test')
    args = parser.parse_args()
    source_url = get_settings().database_url.get_secret_value()
    source = make_url(source_url)
    target_name = args.target_database or f"{source.database}_restore_test"
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,49}_restore_test', target_name) or target_name == source.database:
        parser.error('Use a distinct database name ending in _restore_test, at most 63 characters')
    with psycopg.connect(os.environ.get("ADMIN_DATABASE_URL", "host=127.0.0.1 dbname=postgres user=postgres"), autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_name,)).fetchone():
            raise SystemExit("Recovery-test database exists. Existing data was preserved; use a fresh target for another drill.")
        connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(target_name), sql.Identifier(source.username)))
    latest = create_backup(get_settings().backup_directory)
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
