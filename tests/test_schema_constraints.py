"""The database enforces the rules itself, not only the Python above it.

Each test writes with raw SQL, going around the repositories, and expects
the database to refuse. That is the point of a constraint: the check holds
for every writer - a script, a migration, a future bug - and holds under
concurrency, where a read-then-write check in Python races.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import Database


@pytest.fixture
def sql(db: Database):
    """Run statements in one transaction that is always rolled back."""

    def run(*statements: str, **params) -> None:
        with db.engine.connect() as connection:
            try:
                for statement in statements:
                    connection.execute(text(statement), params)
            finally:
                connection.rollback()

    return run


@pytest.fixture
def owner(db: Database) -> int:
    with db.engine.begin() as connection:
        return connection.execute(
            text("INSERT INTO users (is_guest) VALUES (false) RETURNING id")
        ).scalar_one()


def _meal(owner: int, name: str = "Spaghetti", meal_id: int = 1) -> str:
    return (
        f"INSERT INTO meals (id, user_id, name, servings) "
        f"VALUES ({meal_id}, {owner}, '{name}', 4)"
    )


def test_one_person_cannot_have_two_meals_named_alike(sql, owner):
    with pytest.raises(IntegrityError):
        sql(_meal(owner, "Spaghetti", 1), _meal(owner, "SPAGHETTI", 2))


def test_one_person_cannot_have_two_ingredients_named_alike(sql, owner):
    with pytest.raises(IntegrityError):
        sql(
            f"INSERT INTO ingredients (user_id, name) VALUES ({owner}, 'Eggs')",
            f"INSERT INTO ingredients (user_id, name) VALUES ({owner}, 'eggs')",
        )


@pytest.mark.parametrize("qty", [0, -1])
def test_an_ingredient_line_needs_a_positive_quantity(sql, owner, qty):
    with pytest.raises(IntegrityError):
        sql(
            _meal(owner),
            f"INSERT INTO ingredients (id, user_id, name) VALUES (1, {owner}, 'Pasta')",
            f"INSERT INTO meal_ingredients (meal_id, ingredient_id, qty) VALUES (1, 1, {qty})",
        )


def test_a_meal_serves_at_least_one(sql, owner):
    with pytest.raises(IntegrityError):
        sql(f"INSERT INTO meals (user_id, name, servings) VALUES ({owner}, 'X', 0)")


@pytest.mark.parametrize("day", ["Funday", "monday", ""])
def test_a_plan_day_must_be_a_weekday(sql, owner, day):
    with pytest.raises(IntegrityError):
        sql(
            "INSERT INTO weekly_plans (user_id, week_start_date, day_of_week) "
            f"VALUES ({owner}, '2026-08-03', '{day}')"
        )


def test_one_person_has_one_row_per_day(sql, owner):
    insert = (
        "INSERT INTO weekly_plans (user_id, week_start_date, day_of_week) "
        f"VALUES ({owner}, '2026-08-03', 'Monday')"
    )
    with pytest.raises(IntegrityError):
        sql(insert, insert)


def test_emails_are_unique_ignoring_case(sql):
    with pytest.raises(IntegrityError):
        sql(
            "INSERT INTO users (email, password_hash, is_guest) "
            "VALUES ('Riley@example.com', 'h', false)",
            "INSERT INTO users (email, password_hash, is_guest) "
            "VALUES ('riley@example.com', 'h', false)",
        )


@pytest.mark.parametrize(
    ("email", "password_hash", "is_guest"),
    [
        ("a@example.com", None, False),  # an email with no password
        (None, "h", False),  # a password with no email
        ("a@example.com", "h", True),  # a guest with credentials
    ],
)
def test_account_credentials_are_all_or_nothing(sql, email, password_hash, is_guest):
    with pytest.raises(IntegrityError):
        sql(
            "INSERT INTO users (email, password_hash, is_guest) "
            "VALUES (:email, :password_hash, :is_guest)",
            email=email,
            password_hash=password_hash,
            is_guest=is_guest,
        )


def test_a_plan_cannot_point_at_a_meal_that_does_not_exist(sql, owner):
    """SQLite ignores foreign keys unless told otherwise; the app tells it,
    so local development behaves like Postgres here."""
    with pytest.raises(IntegrityError):
        sql(
            "INSERT INTO weekly_plans (user_id, week_start_date, day_of_week, meal_id) "
            f"VALUES ({owner}, '2026-08-03', 'Monday', 999)"
        )


def test_deleting_a_meal_cascades_and_clears_days(db: Database, owner):
    """The ON DELETE actions, exercised directly: ingredient lines go with
    the meal, and the day it was planned on stays, cleared."""
    with db.engine.begin() as connection:
        for statement in (
            _meal(owner),
            f"INSERT INTO ingredients (id, user_id, name) VALUES (1, {owner}, 'Pasta')",
            "INSERT INTO meal_ingredients (meal_id, ingredient_id, qty) VALUES (1, 1, 200)",
            "INSERT INTO weekly_plans (user_id, week_start_date, day_of_week, meal_id) "
            f"VALUES ({owner}, '2026-08-03', 'Monday', 1)",
        ):
            connection.execute(text(statement))

    with db.engine.begin() as connection:
        connection.execute(text("DELETE FROM meals WHERE id = 1"))

    with db.engine.connect() as connection:
        lines = connection.execute(text("SELECT count(*) FROM meal_ingredients"))
        days = connection.execute(text("SELECT meal_id FROM weekly_plans")).all()
    assert lines.scalar_one() == 0
    assert days == [(None,)]


def test_deleting_an_account_deletes_everything_it_owns(db: Database, owner):
    with db.engine.begin() as connection:
        for statement in (
            _meal(owner),
            f"INSERT INTO ingredients (id, user_id, name) VALUES (1, {owner}, 'Pasta')",
            "INSERT INTO meal_ingredients (meal_id, ingredient_id, qty) VALUES (1, 1, 200)",
            "INSERT INTO weekly_plans (user_id, week_start_date, day_of_week, meal_id) "
            f"VALUES ({owner}, '2026-08-03', 'Monday', 1)",
            "INSERT INTO sessions (token_hash, user_id, expires_at) "
            f"VALUES ('abc', {owner}, '2030-01-01')",
        ):
            connection.execute(text(statement))

    with db.engine.begin() as connection:
        connection.execute(text(f"DELETE FROM users WHERE id = {owner}"))

    with db.engine.connect() as connection:
        for table in (
            "meals",
            "ingredients",
            "meal_ingredients",
            "weekly_plans",
            "sessions",
        ):
            count = connection.execute(text(f"SELECT count(*) FROM {table}"))
            assert count.scalar_one() == 0, table
