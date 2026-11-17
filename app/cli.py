"""Commands for whoever runs the deployment.

    python -m app.cli claim-account

claim-account: the accounts migration gave everything that existed before
accounts to one "unclaimed owner", an account with no email or password,
because a migration must not contain a secret. This gives it both, through
the same checks as signing up, after which its owner logs in normally.

The password is read with getpass: never from the command line, where it
would be saved in shell history and visible to other processes, and never
printed. Like the jobs, this connects as the database owner, and a database
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

    say(f"The unclaimed account holds {meals} meal{'s' if meals != 1 else ''}.")
    email = ask("Email to log in with: ").strip()
    password = ask_secret("Password: ")
    if ask_secret("Same password again: ") != password:
        say("The passwords didn't match. Nothing was changed.")
        return 1
    if ask(f'Give this account to {email}? Type "yes" to continue: ').strip() != "yes":
        say("Nothing was changed.")
        return 1

    try:
        with db.transaction() as session:
            AuthService(session, now=now).claim(owner_id, email, password)
    except MealPlannerError as error:
        say(f"{error} Nothing was changed.")
        return 1

    say(f"Done. Log in as {email.lower()} to see your meals.")
    return 0


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
    commands.add_parser("claim-account", help="give the pre-accounts data a login")
    parser.parse_args(argv)

    # Its own process, so its own log output: the security event it records
    # (app/events.py) goes to stderr, alongside what it prints.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    url = resolve_migration_url(None)
    say(f"Target database: {make_url(url).render_as_string(hide_password=True)}")
    return claim_account(
        Database(url),
        ask=ask,
        ask_secret=ask_secret,
        say=say,
        now=now or datetime.now(UTC),
    )


if __name__ == "__main__":
    sys.exit(main())
