"""Which database a migration run touches, and when it refuses.

A rehearsal meant for a Neon branch once migrated production: the shell
variable was never set, and the alembic CLI fell back to `.env`. These pin
the rule that came out of it: a database not on this machine is migrated
only when named for that run, never by fallback, and never by a dev server
starting up.
"""

from __future__ import annotations

import pytest

import app.migrations as migrations
from app.db import DATABASE_URL_ENV_VAR, is_local_database
from server.main import AUTO_MIGRATE_ENV_VAR, _auto_migrate_enabled

LOCAL_SQLITE = "sqlite:///data/data.db"
LOCAL_POSTGRES = "postgresql+psycopg://postgres:postgres@localhost:5432/mealplanner"
NEON = "postgresql+psycopg://u:p@ep-x-pooler.ap-southeast-2.aws.neon.tech/neondb"


@pytest.mark.parametrize(
    ("url", "local"),
    [
        (LOCAL_SQLITE, True),
        ("sqlite://", True),
        (LOCAL_POSTGRES, True),
        ("postgresql+psycopg://u:p@127.0.0.1:55432/x", True),
        (NEON, False),
        ("postgresql+psycopg://u:p@db.example.com/x", False),
    ],
)
def test_is_local_database(url: str, local: bool) -> None:
    assert is_local_database(url) is local


@pytest.fixture
def no_shell_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENV_VAR, raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)


def _env_file_says(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    """Stand in for a .env file holding `url`, without reading the real one."""
    monkeypatch.setattr(
        migrations,
        "load_env_file",
        lambda: monkeypatch.setenv(DATABASE_URL_ENV_VAR, url),
    )


def test_a_shared_database_from_env_file_is_refused(
    no_shell_url: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env_file_says(monkeypatch, NEON)

    with pytest.raises(SystemExit) as refused:
        migrations.resolve_migration_url(None)

    message = str(refused.value)
    assert "ep-x-pooler.ap-southeast-2.aws.neon.tech/neondb" in message
    assert ":p@" not in message, "the refusal must not print the password"


def test_a_local_database_from_env_file_is_allowed(
    no_shell_url: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env_file_says(monkeypatch, LOCAL_POSTGRES)

    assert migrations.resolve_migration_url(None) == LOCAL_POSTGRES


def test_a_shared_database_set_in_the_shell_is_allowed(
    no_shell_url: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The CI migrate job and a deliberate rehearsal both work this way.
    _env_file_says(monkeypatch, LOCAL_POSTGRES)
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, NEON)

    assert migrations.resolve_migration_url(None) == NEON


def test_a_url_handed_over_from_python_wins(
    no_shell_url: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATABASE_URL_ENV_VAR, LOCAL_POSTGRES)

    assert migrations.resolve_migration_url(NEON) == NEON


@pytest.mark.parametrize(
    ("url", "on_vercel", "setting", "expected"),
    [
        (LOCAL_SQLITE, False, None, True),
        (LOCAL_POSTGRES, False, None, True),
        (NEON, False, None, False),  # dev server with .env -> production
        (LOCAL_SQLITE, True, None, False),
        (NEON, False, "true", True),  # asked for explicitly
        (LOCAL_SQLITE, False, "false", False),
    ],
)
def test_startup_migrates_only_local_databases_unless_told(
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    on_vercel: bool,
    setting: str | None,
    expected: bool,
) -> None:
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv(AUTO_MIGRATE_ENV_VAR, raising=False)
    if on_vercel:
        monkeypatch.setenv("VERCEL", "1")
    if setting is not None:
        monkeypatch.setenv(AUTO_MIGRATE_ENV_VAR, setting)

    assert _auto_migrate_enabled(url) is expected
