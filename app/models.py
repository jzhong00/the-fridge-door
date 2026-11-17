"""SQLModel tables and the domain enums they use.

Deliberately omits ``from __future__ import annotations``: SQLModel reads
these annotations at class-creation time to build the columns, and
stringifying them breaks that.

There are no ORM ``Relationship`` declarations. Every read that needs a
meal with its ingredients is an explicit join in
:mod:`app.repositories`, which is what keeps a week's grocery list to one
query instead of lazy-loading one per row.
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class _HasId(Protocol):
    id: int | None


def persisted_id(row: _HasId) -> int:
    """The primary key of a row that has been flushed or loaded.

    SQLModel types ``id`` as ``int | None`` because a row has no key until
    the database assigns one. Past that point a missing key is a bug, and
    this says so rather than letting ``None`` travel on into a query or a
    response.
    """
    if row.id is None:
        raise RuntimeError(f"{type(row).__name__} has no id; was it flushed?")
    return row.id


class DayOfWeek(StrEnum):
    """The seven days. Declaration order is display order, so `list(DayOfWeek)`
    is the single source of truth for "Monday first"."""

    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"
    SUNDAY = "Sunday"


class MealIngredient(SQLModel, table=True):
    """Pairs a meal with an ingredient, and how much of it."""

    meal_id: int | None = Field(default=None, foreign_key="meal.id", primary_key=True)
    ingredient_id: int | None = Field(
        default=None, foreign_key="ingredient.id", primary_key=True
    )

    qty: float | None = None
    unit: str | None = None


class Meal(SQLModel, table=True):
    """A recipe: a name, the servings it yields, and its ingredients."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    servings: int = 1
    # sa_type is explicit because the default maps to a naive column, and
    # Postgres would then drop the UTC offset. Invisible on SQLite.
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        # SQLModel's annotation only admits a type here, but an instance is
        # what carries timezone=True, and SQLModel accepts one at runtime.
        sa_type=DateTime(timezone=True),  # pyright: ignore[reportArgumentType]
    )


class Ingredient(SQLModel, table=True):
    """A shopping item, shared across every meal that uses it."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)


class WeeklyPlan(SQLModel, table=True):
    """The meal assigned to one day of one week.

    Keyed by (week_start_date, day_of_week), so planning next week never
    overwrites this one.
    """

    __table_args__ = (
        UniqueConstraint(
            "week_start_date", "day_of_week", name="uq_weeklyplan_week_day"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    week_start_date: date = Field(index=True)
    day_of_week: str = Field(index=True)
    meal_id: int | None = Field(default=None, foreign_key="meal.id")
    #: Servings planned for this day. None means use the recipe unscaled.
    servings: int | None = None
