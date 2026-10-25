"""Account administration from the command line.

    python -m backend.manage create-user --email you@example.com --name "Your Name" --role admin
    python -m backend.manage set-password --email you@example.com

Passwords are prompted for (hidden) unless ``--password-stdin`` is given for scripts.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from pydantic import ValidationError

from . import auth, crud, schemas
from .database import SessionLocal, run_migrations


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    password = getpass.getpass("Password (12+ characters): ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords did not match.")
    return password


def _validation_message(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())


def create_user(args: argparse.Namespace) -> int:
    try:
        payload = schemas.UserCreate(
            email=args.email, full_name=args.name, password=_read_password(args.password_stdin), role=args.role
        )
    except ValidationError as error:
        print(f"Invalid input: {_validation_message(error)}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        if crud.get_user_by_email(db, payload.email) is not None:
            print(f"A user with email {payload.email} already exists.", file=sys.stderr)
            return 1
        user = crud.create_user(db, payload, auth.hash_password(payload.password))
    print(f"Created {user.role} {user.email} (id {user.id}).")
    return 0


def set_password(args: argparse.Namespace) -> int:
    password = _read_password(args.password_stdin)
    try:
        schemas.UserUpdate(password=password)
    except ValidationError as error:
        print(f"Invalid input: {_validation_message(error)}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        user = crud.get_user_by_email(db, args.email)
        if user is None:
            print(f"No user with email {args.email}.", file=sys.stderr)
            return 1
        crud.set_password_hash(db, user, auth.hash_password(password), revoke_sessions=True)
    print(f"Password updated for {args.email}; their existing sessions were signed out.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage StudyTrack user accounts.")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-user", help="add an account that can sign in")
    create.add_argument("--email", required=True)
    create.add_argument("--name", default="Administrator", help="full name shown in the app")
    create.add_argument("--role", choices=["admin", "member"], default="member")
    create.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    create.set_defaults(handler=create_user)

    reset = commands.add_parser("set-password", help="set a new password for an existing account")
    reset.add_argument("--email", required=True)
    reset.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    reset.set_defaults(handler=set_password)

    args = parser.parse_args(argv)
    run_migrations()
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
