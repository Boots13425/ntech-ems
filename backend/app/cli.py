"""Administrative operations. Passwords are read interactively or from stdin."""
import argparse
import getpass
import sys

from pydantic import EmailStr, TypeAdapter
from sqlalchemy import delete, select, text

from app.core.permissions import seed_access
from app.core.security import audit, hash_password
from app.db.session import SessionLocal
from app.models import RecoveryCode, Role, Session, User


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed-access", "bootstrap-ceo", "recover-ceo"])
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--password-stdin", action="store_true")
    args = parser.parse_args()
    if args.command == "recover-ceo":
        email = str(TypeAdapter(EmailStr).validate_python(args.email or input("CEO email: "))).casefold()
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email).with_for_update())
            if not user or not user.is_active or not any(role.name == "CEO" for role in user.roles):
                parser.error("No active CEO account exists for that email")
            password = getpass.getpass("New password (12-128 characters): ")
            if password != getpass.getpass("Confirm new password: "):
                parser.error("Passwords do not match; no changes made")
            if not 12 <= len(password) <= 128:
                parser.error("Use a 12-128 character password; no changes made")
            user.password_hash = hash_password(password)
            user.must_change_password = False
            user.mfa_secret = None
            user.mfa_enabled = False
            user.mfa_last_counter = None
            db.execute(delete(Session).where(Session.user_id == user.id))
            db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
            audit(db, None, "auth.ceo_recovered_by_cli", entity_id=user.id)
            db.commit()
        print("CEO access reset. Sign in with your new password, enroll your authenticator, and save the new recovery codes. Previous sessions and recovery codes are revoked.")
        return
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
