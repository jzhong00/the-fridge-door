"""Applying Alembic migrations from Python, for use at application startup."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from app.db import (
    DATABASE_URL_ENV_VAR,
    default_database_url,
    is_local_database,
    load_env_file,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


def resolve_migration_url(handed_over: str | None) -> str:
    """The database a migration run targets, refusing shared ones by default.

    A URL handed over from Python, or set in the shell running `alembic`,
    was chosen for this run and is used as given. Without one, the URL falls
    back to `.env` and then to local SQLite, and a fallback that lands on a
    database not on this machine is refused: on 17 Nov 2026 an `export` that
    silently failed left the shell variable unset, `.env` pointed at
    production, and a rehearsal meant for a Neon branch migrated production.
    """
    chosen = handed_over or os.getenv(DATABASE_URL_ENV_VAR)
    if chosen:
        return chosen

    load_env_file()
    url = default_database_url()
    if not is_local_database(url):
        raise SystemExit(
            f"Refusing to run against {_describe(url)}: {DATABASE_URL_ENV_VAR} is not "
            "set in this shell, and the fallback from .env is not a database on "
            "this machine. To migrate it on purpose, set the variable in this "
            "shell, with the URL in single quotes, and check it with "
            "`python3 scripts/db_report.py` first."
        )
    return url


def _describe(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.host}/{parsed.database}"


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    # Explicit so the location does not depend on the working directory.
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Alembic stores options in a configparser, where % starts an
    # interpolation token; Postgres passwords are often percent-encoded.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    # Read by migrations/env.py in preference to the environment, so the URL
    # passed here is the database migrated, not whatever the env var says.
    config.attributes["database_url"] = url
    return config


def upgrade_to_head(url: str) -> None:
    """Bring the database up to the newest revision.

    A no-op when already current, and allowed to raise: a schema that does
    not match the code should stop startup, not serve errors quietly.
    """
    command.upgrade(_alembic_config(url), "head")


def stamp_head(url: str) -> None:
    """Mark the database as current without running anything.

    For tests, which build their schema from the models; without it the
    startup upgrade would try to create tables that already exist.
    """
    command.stamp(_alembic_config(url), "head")


def upgrade_to(url: str, revision: str) -> None:
    """Upgrade to a specific revision. For migration tests."""
    command.upgrade(_alembic_config(url), revision)


def downgrade_to(url: str, revision: str) -> None:
    """Downgrade to a specific revision. For migration tests."""
    command.downgrade(_alembic_config(url), revision)
