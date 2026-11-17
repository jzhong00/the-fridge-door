"""The suite empties whatever database TEST_DATABASE_URL names, so it must
refuse anything that is not plainly a throwaway test database."""

from __future__ import annotations

import pytest
from database_safety import assert_disposable, check_test_database_settings


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://postgres:postgres@localhost:5432/mealplanner_test",
        "postgresql+psycopg://u:p@ep-x-pooler.ap-southeast-2.aws.neon.tech/app_test?sslmode=require",
    ],
)
def test_a_database_named_for_tests_is_accepted(url):
    assert_disposable(url)


@pytest.mark.parametrize(
    "url",
    [
        # The production database on Neon is called neondb.
        "postgresql+psycopg://u:p@ep-x-pooler.ap-southeast-2.aws.neon.tech/neondb?sslmode=require",
        "postgresql+psycopg://postgres:postgres@localhost:5432/mealplanner",
        "postgresql+psycopg://postgres:postgres@localhost:5432/test_mealplanner",
        "postgresql+psycopg://postgres:postgres@localhost:5432/",
    ],
)
def test_any_other_database_is_refused_before_anything_is_dropped(url):
    with pytest.raises(pytest.UsageError, match="_test"):
        assert_disposable(url)


def test_the_refusal_never_echoes_the_password():
    url = "postgresql+psycopg://admin:hunter2@db.example.com/neondb"

    with pytest.raises(pytest.UsageError) as refused:
        assert_disposable(url)

    assert "hunter2" not in str(refused.value)


def test_requiring_a_database_without_one_is_an_error():
    """The Postgres CI leg sets REQUIRE_TEST_DATABASE so a missing URL fails
    loudly instead of quietly running the SQLite suite and passing."""
    with pytest.raises(pytest.UsageError, match="TEST_DATABASE_URL"):
        check_test_database_settings(url=None, required=True)


def test_without_a_url_or_a_requirement_the_suite_uses_sqlite():
    check_test_database_settings(url=None, required=False)
