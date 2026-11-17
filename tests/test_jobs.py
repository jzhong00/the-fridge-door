"""The scheduled purge: what it removes, and everything it must leave alone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, text, update
from sqlmodel import col, select

from app import jobs, migrations
from app.db import DATABASE_URL_ENV_VAR, Database
from app.models import Meal, RateLimit, User
from app.models import Session as SessionRow
from app.repositories import MealRepository, UserRepository

NOW = datetime(2026, 9, 1, 3, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def _user(db: Database, *, guest: bool, seen_days_ago: int, email: str | None = None):
    with db.transaction() as session:
        users = UserRepository(session)
        user = users.create(is_guest=guest)
        if email:
            users.set_credentials(user, email, "not-a-real-hash")
        user_id = user.id or 0
        MealRepository(session, user_id=user_id).add(f"Meal of {user_id}")
        session.execute(
            update(User)
            .where(col(User.id) == user_id)
            .values(last_seen_at=NOW - seen_days_ago * DAY)
        )
    return user_id


@pytest.fixture
def world(db: Database) -> dict[str, int]:
    ids = {
        "idle_guest": _user(db, guest=True, seen_days_ago=31),
        "recent_guest": _user(db, guest=True, seen_days_ago=29),
        "idle_account": _user(db, guest=False, seen_days_ago=400, email="a@b.co"),
        "unclaimed_owner": _user(db, guest=False, seen_days_ago=400),
    }
    with db.transaction() as session:
        session.add(
            SessionRow(
                token_hash="expired",
                user_id=ids["recent_guest"],
                expires_at=NOW - timedelta(minutes=1),
            )
        )
        session.add(
            SessionRow(
                token_hash="live", user_id=ids["idle_account"], expires_at=NOW + DAY
            )
        )
        session.add(
            SessionRow(
                token_hash="idle-guests",
                user_id=ids["idle_guest"],
                expires_at=NOW + DAY,
            )
        )
        session.add(
            RateLimit(
                scope="s", subject="stale", hits=3, window_started_at=NOW - 2 * DAY
            )
        )
        session.add(
            RateLimit(
                scope="s",
                subject="recent",
                hits=3,
                window_started_at=NOW - timedelta(hours=1),
            )
        )
        session.add(
            RateLimit(
                scope="s",
                subject="old-but-blocked",
                hits=9,
                window_started_at=NOW - 2 * DAY,
                blocked_until=NOW + timedelta(minutes=5),
            )
        )
    return ids


def _remaining(db: Database, model, column) -> set:
    with db.transaction() as session:
        return set(session.exec(select(column)).all())


def _purge(db: Database, *, dry_run: bool) -> jobs.Purged:
    with db.transaction() as session:
        return jobs.purge_guests(session, now=NOW, dry_run=dry_run)


def test_a_dry_run_counts_and_deletes_nothing(db, world):
    assert _purge(db, dry_run=True) == jobs.Purged(guests=1, sessions=1, rate_limits=1)
    assert len(_remaining(db, User, User.id)) == 4
    assert len(_remaining(db, SessionRow, SessionRow.token_hash)) == 3


def test_idle_guests_go_with_everything_they_made(db, world):
    assert _purge(db, dry_run=False) == jobs.Purged(guests=1, sessions=1, rate_limits=1)

    assert _remaining(db, User, User.id) == {
        world["recent_guest"],
        world["idle_account"],
        world["unclaimed_owner"],
    }
    # Their meal and their (still unexpired) session went with them.
    owners = _remaining(db, Meal, Meal.user_id)
    assert world["idle_guest"] not in owners and len(owners) == 3
    assert _remaining(db, SessionRow, SessionRow.token_hash) == {"live"}


def test_accounts_and_the_unclaimed_owner_are_never_purged_however_idle(db, world):
    _purge(db, dry_run=False)
    users = _remaining(db, User, User.id)
    assert {world["idle_account"], world["unclaimed_owner"]} <= users


def test_only_rate_limits_that_can_no_longer_matter_go(db, world):
    _purge(db, dry_run=False)
    assert _remaining(db, RateLimit, RateLimit.subject) == {"recent", "old-but-blocked"}


def test_running_twice_finds_nothing_the_second_time(db, world):
    _purge(db, dry_run=False)
    assert _purge(db, dry_run=False) == jobs.Purged(guests=0, sessions=0, rate_limits=0)


def test_the_command_line_reports_and_logs_what_it_did(db, world, capsys):
    assert jobs.main(["purge-guests"], now=NOW) == 0

    output = capsys.readouterr().out
    # Says where it ran, without the password (Postgres shows it masked).
    assert "Target database: " in output
    assert ":postgres@" not in output
    assert "Removed: 1 guests, 1 sessions, 1 rate limits" in output
    with db.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM users")).scalar() == 3


def test_the_command_line_dry_run_says_would(db, world, capsys):
    jobs.main(["purge-guests", "--dry-run"], now=NOW)
    assert "Would remove: 1 guests" in capsys.readouterr().out
    with db.transaction() as session:
        assert session.execute(select(func.count()).select_from(User)).scalar() == 4


def test_the_job_refuses_a_shared_database_it_was_not_told_about(monkeypatch):
    # The same guard as migrations: a database not on this machine must be
    # named in the shell, never picked up from .env.
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.setattr(
        migrations,
        "load_env_file",
        lambda: monkeypatch.setenv(
            DATABASE_URL_ENV_VAR, "postgresql+psycopg://u:p@ep-x.neon.tech/neondb"
        ),
    )
    with pytest.raises(SystemExit, match="Refusing"):
        jobs.main(["purge-guests"], now=NOW)
