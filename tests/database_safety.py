"""Guards the test suite against emptying a database that matters.

When TEST_DATABASE_URL is set, the `db` fixture drops every table in that
database before each test. Pointed at production by mistake - a copied
.env, a shell variable left over from a migration - it would wipe it. So the
suite refuses to start unless the database's name ends in `_test`.

The same convention guards FloorSync's integration harness.
"""

from __future__ import annotations

import pytest
from sqlalchemy import make_url

DISPOSABLE_SUFFIX = "_test"


def assert_disposable(url: str) -> None:
    """Raise unless `url` names a database that is safe to empty."""
    parsed = make_url(url)
    name = parsed.database or ""
    if not name.endswith(DISPOSABLE_SUFFIX):
        # render_as_string hides the password, so the refusal is safe to log.
        shown = parsed.render_as_string(hide_password=True)
        raise pytest.UsageError(
            f"Refusing to run against {shown}: the suite drops every table in "
            f"TEST_DATABASE_URL, so the database name must end in "
            f"'{DISPOSABLE_SUFFIX}'."
        )


def check_test_database_settings(*, url: str | None, required: bool) -> None:
    """Validate the configuration once, before any test runs.

    `required` is for a CI job that started Postgres precisely to run the
    suite against it: without a URL it would quietly fall back to SQLite and
    pass, proving nothing about Postgres.
    """
    if url:
        assert_disposable(url)
    elif required:
        raise pytest.UsageError(
            "REQUIRE_TEST_DATABASE is set but TEST_DATABASE_URL is empty, so "
            "the suite would silently run on SQLite instead."
        )
