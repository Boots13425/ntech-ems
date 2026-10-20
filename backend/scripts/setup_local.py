"""Optional local PostgreSQL provisioning; never writes or prints admin credentials."""
import os
import secrets
from pathlib import Path

import psycopg
from cryptography.fernet import Fernet
from psycopg import sql


def main():
    root = Path(__file__).resolve().parents[1]
    env_path = root / ".env"
    if env_path.exists():
        raise SystemExit("backend/.env already exists. Existing configuration was preserved.")
    password = secrets.token_urlsafe(40)
    # libpq reads PGHOST/PGPORT/PGUSER/PGPASSFILE; an optional DSN is read only from the environment.
    with psycopg.connect(os.environ.get("ADMIN_DATABASE_URL", "host=127.0.0.1 dbname=postgres user=postgres"), autocommit=True) as connection:
        if connection.execute("SELECT 1 FROM pg_roles WHERE rolname = 'ntech_ems'").fetchone():
            raise SystemExit("The ntech_ems database role exists. Configure .env manually; no existing role was changed.")
        if connection.execute("SELECT 1 FROM pg_database WHERE datname IN ('ntech_ems', 'ntech_ems_test')").fetchone():
            raise SystemExit("An EMS database already exists. Configure .env manually; no existing database was changed.")
        connection.execute(sql.SQL("CREATE ROLE ntech_ems LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(sql.Literal(password)))
        for database in ["ntech_ems", "ntech_ems_test"]:
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER ntech_ems").format(sql.Identifier(database)))
    contents = (root / ".env.example").read_text().replace("CHANGE_ME", password).replace("GENERATE_A_FERNET_KEY", Fernet.generate_key().decode()).replace("GENERATE_A_SEPARATE_BACKUP_KEY", Fernet.generate_key().decode())
    env_path.write_text(contents, encoding="utf-8")
    print("Local application and test databases created; secrets saved only in ignored backend/.env.")


if __name__ == "__main__":
    main()
