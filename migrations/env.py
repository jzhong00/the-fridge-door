"""Alembic environment.

Targets whatever database the application targets: the URL comes from
MEAL_PLANNER_DB_URL, falling back to the local SQLite file, so `alembic`
run by hand and the migration run at app startup can never disagree.
"""

import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel

# Importing the models registers every table on SQLModel.metadata, which is
# what autogenerate diffs the live database against.
from app import models  # noqa: F401
from app.migrations import resolve_migration_url

config = context.config

if config.config_file_name is not None:
    # Without disable_existing_loggers=False this silences every logger
    # created before it runs, and the server runs migrations at startup,
    # so the API's own error logging went quiet the moment it booted.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# A URL handed over by app.migrations wins (before the attribute existed, a
# URL passed to upgrade_to_head() was silently ignored), then the shell's
# MEAL_PLANNER_DB_URL, then .env, which may only name a local database.
_url = resolve_migration_url(config.attributes.get("database_url"))

# Every run says which database it is about to change, before changing it.
logging.getLogger("alembic.env").info(
    "Target database: %s", make_url(_url).render_as_string(hide_password=True)
)

# configparser treats % as interpolation syntax, and Postgres passwords are
# percent-encoded, so any literal % has to be escaped before being stored.
config.set_main_option("sqlalchemy.url", _url.replace("%", "%%"))

target_metadata = SQLModel.metadata


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or manual apply."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        # SQLite cannot ALTER most things in place; batch mode rebuilds the
        # table instead. Harmless to leave on only where it is needed.
        render_as_batch=_is_sqlite(url or ""),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
