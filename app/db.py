"""Database engine ownership and transactional sessions."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, event
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine

# Registers the tables on SQLModel.metadata for create_tables().
from app import models  # noqa: F401

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DATABASE_URL_ENV_VAR = "MEAL_PLANNER_DB_URL"


def load_env_file() -> None:
    """Load .env for local development. A no-op if python-dotenv is absent."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


def default_database_url() -> str:
    """The configured database URL, falling back to a local SQLite file."""
    configured = os.getenv(DATABASE_URL_ENV_VAR)
    if configured:
        return configured

    # Serverless filesystems are read-only outside /tmp, so the SQLite
    # fallback cannot work there; say so rather than failing in mkdir.
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        raise RuntimeError(
            f"{DATABASE_URL_ENV_VAR} is not set. A serverless deployment has no "
            "writable disk for the SQLite fallback, so a Postgres URL is "
            "required. Set it for this environment in the platform's settings."
        )

    DEFAULT_DATA_DIR.mkdir(exist_ok=True)
    return f"sqlite:///{DEFAULT_DATA_DIR / 'data.db'}"


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def is_local_database(url: str) -> bool:
    """Whether the database lives on this machine: SQLite, or a server on
    localhost such as the Docker container or CI's service container.

    Anything else (Neon, production or a branch) is shared, and is only
    ever migrated when someone names it on purpose.
    """
    parsed = make_url(url)
    return parsed.get_backend_name() == "sqlite" or parsed.host in _LOCAL_HOSTS


def _enforce_sqlite_foreign_keys(engine: Engine) -> None:
    """Make SQLite enforce foreign keys, as Postgres always does.

    SQLite ignores them unless asked, per connection. Without this, local
    development and the SQLite test leg would accept rows pointing at
    nothing and skip every ON DELETE action, so behaviour would differ from
    production exactly where it matters. Alembic uses its own engine, so
    migrations that rebuild tables are unaffected.
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection, _record) -> None:  # pyright: ignore[reportUnusedFunction]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Database:
    """Owns an engine and hands out transactional sessions.

    Takes an explicit URL rather than reading a global, so tests can point it
    at a temporary file and deployments at Postgres without touching callers.
    """

    def __init__(self, url: str | None = None, *, echo: bool | None = None) -> None:
        self.url = url or default_database_url()
        if echo is None:
            echo = os.getenv("SQL_ECHO", "false").lower() == "true"

        options: dict[str, object] = {}
        if not self.is_sqlite:
            # A pooler or network can drop an idle connection; check one is
            # alive rather than failing the first query after a quiet period.
            options["pool_pre_ping"] = True
            # Bounded, so a readiness probe or a request against an
            # unreachable database fails in seconds rather than hanging.
            # Generous enough for a Neon compute waking from suspension.
            options["connect_args"] = {"connect_timeout": 10}

        self._engine = create_engine(self.url, echo=echo, **options)
        if self.is_sqlite:
            _enforce_sqlite_foreign_keys(self._engine)

    @property
    def is_sqlite(self) -> bool:
        return self.url.startswith("sqlite")

    @property
    def engine(self) -> Engine:
        """The SQLAlchemy engine, for Alembic and diagnostics."""
        return self._engine

    def create_tables(self) -> None:
        """Create missing tables straight from the models.

        For tests only - replaying the migration history per test would be
        needlessly slow. The app migrates instead, and CI asserts they agree.
        """
        SQLModel.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Generator[Session]:
        """Yield a session that commits on success and rolls back on error."""
        # expire_on_commit=False keeps attributes readable after close, so
        # repositories can return ORM objects to callers with no session.
        session = Session(self._engine, expire_on_commit=False)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
