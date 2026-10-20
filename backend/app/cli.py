"""Administrative operations. Passwords are read interactively or from stdin."""
import argparse
import getpass
import sys

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import select, text

from app.core.permissions import seed_access
from app.core.security import audit, hash_password
from app.db.session import SessionLocal
from app.models import Role, User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed-access", "bootstrap-ceo"])
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(98171621)"))
        seed_access(db)
        if args.command == "bootstrap-ceo":
            if db.scalar(select(User.id).join(User.roles).where(Role.name == "CEO").limit(1)):
                parser.error("A CEO account already exists; use Staff Management for additional accounts")
            email = str(TypeAdapter(EmailStr).validate_python(args.email or input("CEO email: "))).casefold()
            name = (args.name or input("Full name: ")).strip()
            password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("Password (12+ characters): ")
            if not args.password_stdin and password != getpass.getpass("Confirm password: "):
                parser.error("Passwords do not match")
            if not 12 <= len(password) <= 128 or not 2 <= len(name) <= 150:
                parser.error("Use a 12–128 character password and a 2–150 character name")
            user = User(email=email, full_name=name, password_hash=hash_password(password), roles=[db.scalar(select(Role).where(Role.name == "CEO"))])
            db.add(user)
            db.flush()
            audit(db, user, "staff.ceo_bootstrapped", entity_id=user.id)
        db.commit()
    print("Access configuration ready." if args.command == "seed-access" else "CEO account created. Enroll an authenticator at first sign-in.")


if __name__ == "__main__":
    main()
