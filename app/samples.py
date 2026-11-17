"""What a new guest starts with, so the app explains itself on first load.

Three meals from the templates, planned on four days of the guest's current
week. Four rather than seven on purpose: the grocery list has something real
to total straight away, and the empty days show what an unplanned day looks
like. Built from MEAL_TEMPLATES through the same repository calls as the
quick-add button, so there is no second set of demo content to keep in step.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session

from app.models import DayOfWeek, persisted_id
from app.repositories import MealRepository, WeeklyPlanRepository
from app.templates import MEAL_TEMPLATES

SAMPLE_MEALS = ("Spaghetti Bolognese", "Tacos", "Butter Chicken")
#: Day -> (meal, servings planned). Servings differ from the recipe on one
#: day, so the scaling in the grocery list is visible too.
SAMPLE_PLAN = {
    DayOfWeek.MONDAY: ("Spaghetti Bolognese", 4),
    DayOfWeek.TUESDAY: ("Tacos", 2),
    DayOfWeek.THURSDAY: ("Butter Chicken", 4),
    DayOfWeek.SATURDAY: ("Spaghetti Bolognese", 2),
}


def add_samples(session: Session, user_id: int, week: date) -> None:
    """Give a new account the sample meals, planned in the week of `week`.

    The caller must already have declared `user_id` for row-level security
    (`app.db.act_as`); these writes go through the policies like any other.
    """
    week_start = week - timedelta(days=week.weekday())
    templates = {template.name: template for template in MEAL_TEMPLATES}
    meals = MealRepository(session, user_id=user_id)
    ids = {
        name: persisted_id(meals.add_from_template(templates[name]))
        for name in SAMPLE_MEALS
    }
    WeeklyPlanRepository(session, user_id=user_id).set_week(
        week_start,
        {day: (ids[name], servings) for day, (name, servings) in SAMPLE_PLAN.items()},
    )
