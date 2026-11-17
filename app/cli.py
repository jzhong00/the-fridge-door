"""Commands for whoever runs the deployment.

    python -m app.cli claim-account
    python -m app.cli set-password

claim-account: the accounts migration gave everything that existed before
accounts to one "unclaimed owner", an account with no email or password,
because a migration must not contain a secret. This gives it both, through
the same checks as signing up, after which its owner logs in normally.

set-password: a new password for an existing account, through the same
password checks, ending every session the account has. Until password reset
by email exists (Phase 2), this is how a forgotten password is recovered.

Passwords are read with getpass: never from the command line, where they
would be saved in shell history and visible to other processes, and never
printed. Like the jobs, these connect as the database owner, and a database
not on this machine must be named in the shell (`resolve_migration_url`).
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.engine import make_url

from app.auth import AuthService
from app.db import Database
from app.exceptions import MealPlannerError
from app.migrations import resolve_migration_url
from app.models import persisted_id
from app.repositories import MealRepository, UserRepository

Ask = Callable[[str], str]
Say = Callable[[str], None]


def claim_account(
    db: Database, *, ask: Ask, ask_secret: Ask, say: Say, now: datetime
) -> int:
    with db.transaction() as session:
        owners = UserRepository(session).unclaimed_owners()
        if not owners:
            say("There is no unclaimed account. Nothing to do.")
            return 0
        if len(owners) > 1:
            ids = ", ".join(str(persisted_id(owner)) for owner in owners)
            say(f"Expected one unclaimed account, found {len(owners)} ({ids}).")
            return 1
        owner_id = persisted_id(owners[0])
        meals = len(MealRepository(session, user_id=owner_id).list_all())

    say(f"The unclaimed account holds {_count(meals, 'meal')}.")
    email = ask("Email to log in with: ").strip()
    password = _new_password(ask_secret, say)
    if password is None:
        return 1
    if not _confirmed(ask, say, f"Give this account to {email}?"):
        return 1

    try:
        with db.transaction() as session:
            AuthService(session, now=now).claim(owner_id, email, password)
    except MealPlannerError as error:
        say(f"{error} Nothing was changed.")
        return 1

    say(f"Done. Log in as {email.lower()} to see your meals.")
    return 0


def set_password(
    db: Database, *, ask: Ask, ask_secret: Ask, say: Say, now: datetime
) -> int:
    email = ask("Email of the account: ").strip().lower()
    with db.transaction() as session:
        user = UserRepository(session).find_by_email(email)
        if user is None:
            # Saying so is safe here: whoever can run this can read the
            # users table anyway.
            say(f"No account has the email {email}. Nothing was changed.")
            return 1
        user_id = persisted_id(user)

    password = _new_password(ask_secret, say)
    if password is None:
        return 1
    if not _confirmed(
        ask, say, f"Set a new password for {email}, signing it out everywhere?"
    ):
        return 1

    try:
        with db.transaction() as session:
            ended = AuthService(session, now=now).set_password(user_id, password)
    except MealPlannerError as error:
        say(f"{error} Nothing was changed.")
        return 1

    say(
        f"Done. Ended {_count(ended, 'session')}. "
        f"Log in as {email} with the new password."
    )
    return 0


COMMANDS = {
    "claim-account": (claim_account, "give the pre-accounts data a login"),
    "set-password": (set_password, "replace a forgotten password"),
}


def main(
    argv: list[str] | None = None,
    *,
    ask: Ask = input,
    ask_secret: Ask = getpass.getpass,
    say: Say = print,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, (_, help_text) in COMMANDS.items():
        commands.add_parser(name, help=help_text)
    args = parser.parse_args(argv)

    # Its own process, so its own log output: the security events it records
    # (app/events.py) go to stderr, alongside what it prints.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    url = resolve_migration_url(None)
    say(f"Target database: {make_url(url).render_as_string(hide_password=True)}")
    command, _ = COMMANDS[args.command]
    return command(
        Database(url),
        ask=ask,
        ask_secret=ask_secret,
        say=say,
        now=now or datetime.now(UTC),
    )


def _new_password(ask_secret: Ask, say: Say) -> str | None:
    """A password typed twice, or None (having said why) if they differ."""
    password = ask_secret("Password: ")
    if ask_secret("Same password again: ") != password:
        say("The passwords didn't match. Nothing was changed.")
        return None
    return password


def _confirmed(ask: Ask, say: Say, question: str) -> bool:
    if ask(f'{question} Type "yes" to continue: ').strip() == "yes":
        return True
    say("Nothing was changed.")
    return False


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


if __name__ == "__main__":
    sys.exit(main())
