"""Shared fixtures.

Tests run against SQLite by default: a fresh temporary file per test, no
server required. Setting TEST_DATABASE_URL points the same suite at Postgres
instead, which is how CI proves the code is genuinely portable rather than
accidentally SQLite-shaped.

Isolation comes from constructing :class:`~app.db.Database` with an explicit
URL, and from setting that URL in the environment so code building its own
Database (the API) picks it up too. Nothing patches module internals.
"""

from __future__ import annotations

import os

import pytest
from database_safety import assert_disposable, check_test_database_settings
from sqlmodel import SQLModel

from app.db import DATABASE_URL_ENV_VAR, Database
from app.migrations import stamp_head
from app.repositories import (
    IngredientRepository,
    MealRepository,
    UserRepository,
    WeeklyPlanRepository,
)
from server.deps import reset_services_cache

#: Point the suite at a real Postgres. Unset means local SQLite files.
TEST_DATABASE_URL_ENV_VAR = "TEST_DATABASE_URL"
#: Set to "1" where a Postgres run is the point, so a missing URL fails.
REQUIRE_TEST_DATABASE_ENV_VAR = "REQUIRE_TEST_DATABASE"


def pytest_configure(config) -> None:
    """Refuse to start against a database that is not a disposable test one."""
    check_test_database_settings(
        url=os.getenv(TEST_DATABASE_URL_ENV_VAR),
        required=os.getenv(REQUIRE_TEST_DATABASE_ENV_VAR) == "1",
    )


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch) -> Database:
    """A Database isolated to this test, never the app's own data/data.db."""
    shared_url = os.getenv(TEST_DATABASE_URL_ENV_VAR)
    url = shared_url or f"sqlite:///{tmp_path / 'test.db'}"

    monkeypatch.setenv(DATABASE_URL_ENV_VAR, url)

    # The API caches its engine per process, which would otherwise leak one
    # test's connection - and data - into the next.
    reset_services_cache()

    database = Database(url)
    if shared_url:
        # A server-backed database persists between tests, unlike a temp
        # file, so it has to be emptied explicitly. Checked again here, right
        # before the drop, in case the variable changed after startup.
        assert_disposable(shared_url)
        SQLModel.metadata.drop_all(database.engine)

    # Built straight from the models rather than by replaying migrations,
    # which would cost a full DDL run per test. The stamp then tells the
    # application's startup upgrade there is nothing left to apply, and CI
    # separately asserts the migrations and models agree.
    database.create_tables()
    stamp_head(url)
    yield database

    reset_services_cache()


@pytest.fixture
def user_id(db: Database) -> int:
    """The account the repository fixtures act as."""
    return UserRepository(db).create(is_guest=False).id or 0


@pytest.fixture
def other_user_id(db: Database) -> int:
    """A second account, for proving one cannot see the other's data."""
    return UserRepository(db).create(is_guest=False).id or 0


@pytest.fixture
def meals(db: Database, user_id: int) -> MealRepository:
    return MealRepository(db, user_id=user_id)


@pytest.fixture
def ingredients(db: Database, user_id: int) -> IngredientRepository:
    return IngredientRepository(db, user_id=user_id)


@pytest.fixture
def plans(db: Database, user_id: int) -> WeeklyPlanRepository:
    return WeeklyPlanRepository(db, user_id=user_id)
