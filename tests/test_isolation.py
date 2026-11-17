"""One person's data is invisible to everyone else.

Repositories are bound to a user, so every test here builds two of each and
proves neither can read, change or plan with the other's rows. Asking for
someone else's meal must look exactly like asking for one that does not
exist, so the API answers 404 and never confirms the id is real.
"""

from __future__ import annotations

from datetime import date

import pytest
from per_request import PerRequest

from app.db import Database
from app.exceptions import MealNotFoundError
from app.models import DayOfWeek
from app.planner import generate_weekly_grocery_list
from app.repositories import IngredientRepository, MealRepository, WeeklyPlanRepository

WEEK = date(2026, 8, 3)


@pytest.fixture
def their_meals(db: Database, other_user_id: int) -> MealRepository:
    return PerRequest(db, lambda s: MealRepository(s, user_id=other_user_id))  # type: ignore[return-value]


@pytest.fixture
def their_plans(db: Database, other_user_id: int) -> WeeklyPlanRepository:
    return PerRequest(db, lambda s: WeeklyPlanRepository(s, user_id=other_user_id))  # type: ignore[return-value]


@pytest.fixture
def their_ingredients(db: Database, other_user_id: int) -> IngredientRepository:
    return PerRequest(db, lambda s: IngredientRepository(s, user_id=other_user_id))  # type: ignore[return-value]


def test_each_person_sees_only_their_own_meals(meals, their_meals):
    meals.add("Spaghetti")
    their_meals.add("Tacos")

    assert [m.name for m in meals.list_all()] == ["Spaghetti"]
    assert [m.name for m, _ in their_meals.list_all_with_ingredients()] == ["Tacos"]


def test_two_people_can_both_have_a_meal_of_the_same_name(meals, their_meals):
    meals.add("Spaghetti Bolognese")

    their_meals.add("spaghetti bolognese")

    assert len(their_meals.list_all()) == 1


@pytest.mark.parametrize(
    "operation",
    [
        lambda repo, meal_id: repo.get_with_ingredients(meal_id),
        lambda repo, meal_id: repo.update(meal_id, "Mine now", 2),
        lambda repo, meal_id: repo.delete(meal_id),
        lambda repo, meal_id: repo.add_ingredient(meal_id, "Salt", 1, "g"),
        lambda repo, meal_id: repo.update_ingredient(meal_id, 1, 5, "g"),
        lambda repo, meal_id: repo.remove_ingredient(meal_id, 1),
    ],
    ids=["read", "update", "delete", "add ingredient", "edit ingredient", "remove"],
)
def test_someone_elses_meal_does_not_exist(meals, their_meals, operation):
    mine = meals.add("Spaghetti")
    meals.add_ingredient(mine.id, "Pasta", 200, "g")

    with pytest.raises(MealNotFoundError):
        operation(their_meals, mine.id)

    # And nothing about it changed.
    meal, lines = meals.get_with_ingredients(mine.id)
    assert meal.name == "Spaghetti"
    assert [(link.qty, ingredient.name) for link, ingredient in lines] == [
        (200, "Pasta")
    ]


def test_their_ingredient_lines_are_not_listed(meals, their_meals):
    mine = meals.add("Spaghetti")
    meals.add_ingredient(mine.id, "Pasta", 200, "g")

    assert their_meals.list_ingredients(mine.id) == []


def test_no_one_can_plan_someone_elses_meal(meals, their_plans):
    """The foreign key would accept it: a key check does not know who owns
    the row it points at. So the repository checks."""
    mine = meals.add("Spaghetti")

    with pytest.raises(MealNotFoundError):
        their_plans.set_day(WEEK, DayOfWeek.MONDAY, mine.id)

    assert their_plans.get_week(WEEK) == []


def test_two_people_can_both_plan_the_same_monday(
    meals, plans, their_meals, their_plans
):
    """The old schema made (week, day) unique for the whole app, so the
    second person to plan a Monday hit a constraint violation."""
    mine = meals.add("Spaghetti")
    theirs = their_meals.add("Tacos")

    plans.set_day(WEEK, DayOfWeek.MONDAY, mine.id)
    their_plans.set_day(WEEK, DayOfWeek.MONDAY, theirs.id)

    assert [p.meal_id for p in plans.get_week(WEEK)] == [mine.id]
    assert [p.meal_id for p in their_plans.get_week(WEEK)] == [theirs.id]


def test_the_autocomplete_never_suggests_someone_elses_ingredient(
    meals, their_meals, ingredients, their_ingredients
):
    mine = meals.add("Spaghetti")
    meals.add_ingredient(mine.id, "Pasta", 200, "g")
    theirs = their_meals.add("Tacos")
    their_meals.add_ingredient(theirs.id, "Tortillas", 8, "")

    assert [i.name for i in ingredients.list_all()] == ["Pasta"]
    assert [i.name for i in their_ingredients.list_all()] == ["Tortillas"]


def test_the_same_ingredient_name_is_a_separate_row_per_person(meals, their_meals):
    mine = meals.add("Spaghetti")
    theirs = their_meals.add("Carbonara")

    meals.add_ingredient(mine.id, "Pasta", 200, "g")
    their_meals.add_ingredient(theirs.id, "pasta", 300, "g")

    (my_line,) = meals.list_ingredients(mine.id)
    (their_line,) = their_meals.list_ingredients(theirs.id)
    assert my_line[1].id != their_line[1].id


def test_the_grocery_list_totals_only_my_plan(meals, plans, their_meals, their_plans):
    mine = meals.add("Spaghetti")
    meals.add_ingredient(mine.id, "Pasta", 200, "g")
    plans.set_day(WEEK, DayOfWeek.MONDAY, mine.id)
    theirs = their_meals.add("Carbonara")
    their_meals.add_ingredient(theirs.id, "Pasta", 500, "g")
    their_plans.set_day(WEEK, DayOfWeek.MONDAY, theirs.id)

    (line,) = generate_weekly_grocery_list(plans, WEEK)

    assert (line.name, line.display_qty) == ("Pasta", "200 g")


def test_copying_a_week_copies_only_my_days(meals, plans, their_meals, their_plans):
    mine = meals.add("Spaghetti")
    theirs = their_meals.add("Tacos")
    previous = date(2026, 7, 27)
    plans.set_day(previous, DayOfWeek.MONDAY, mine.id)
    their_plans.set_day(previous, DayOfWeek.TUESDAY, theirs.id)

    assert plans.copy_week(previous, WEEK) == 1
    assert [(p.day_of_week, p.meal_id) for p in plans.get_week(WEEK)] == [
        ("Monday", mine.id)
    ]
