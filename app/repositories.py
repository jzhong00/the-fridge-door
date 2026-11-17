"""Data-access layer.

Every repository is bound to one user when it is constructed, and every
query it runs is scoped to that user. There is no method that takes a user
per call, so there is no method where forgetting it is possible: an unscoped
query is not expressible through this module. (Row-level security in
Postgres sits behind this, for the case where that reasoning is wrong.)

Asking for another user's row behaves exactly like asking for a row that
does not exist, so the API answers 404 either way and never confirms that
someone else's id is real.

Each repository takes a :class:`~app.db.Database` and runs every method in
one transaction, so multi-step writes either land completely or not at all.
Passing a session instead runs several repositories in one transaction.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from datetime import date

from sqlalchemy import delete, func, insert, update
from sqlalchemy import select as sa_select
from sqlmodel import Session, col, select

from app.db import Database
from app.exceptions import (
    DuplicateNameError,
    IngredientNotOnMealError,
    InvalidDayError,
    MealNotFoundError,
    UnitMismatchError,
)
from app.models import (
    DayOfWeek,
    Ingredient,
    Meal,
    MealIngredient,
    User,
    WeeklyPlan,
    persisted_id,
)
from app.templates import MealTemplate


def _as_day(day: DayOfWeek | str) -> str:
    """Validate a weekday, returning its canonical name."""
    try:
        return DayOfWeek(day).value
    except ValueError:
        raise InvalidDayError(f"'{day}' is not a day of the week.") from None


class _Repository:
    """Common session handling and the user every query is scoped to.

    Each method opens a session, which normally means one transaction per
    call. A caller that wants several calls in one transaction passes the
    session in, and every method here joins it instead - one BEGIN/COMMIT
    per request rather than one per repository touched.
    """

    def __init__(
        self, db: Database, session: Session | None = None, *, user_id: int
    ) -> None:
        self._db = db
        self._session_override = session
        self._user_id = user_id

    @property
    def user_id(self) -> int:
        return self._user_id

    def _session(self) -> AbstractContextManager[Session]:
        if self._session_override is not None:
            # Not ours to commit or close; the owner does both.
            return nullcontext(self._session_override)
        return self._db.session()


class IngredientRepository(_Repository):
    """Reads over one user's ingredients."""

    def list_all(self) -> list[Ingredient]:
        """Every ingredient this user has used, for the autocomplete."""
        with self._session() as session:
            return list(
                session.exec(
                    select(Ingredient).where(Ingredient.user_id == self._user_id)
                ).all()
            )


class MealRepository(_Repository):
    """Creates, reads and edits one user's meals and their ingredients."""

    # ------------------------------------------------------------- meals

    def list_all(self) -> list[Meal]:
        """Every meal this user has saved, oldest first.

        Ordered explicitly: without ORDER BY the database may return rows in
        any order, and the per-user name index made SQLite return them
        alphabetically, reshuffling the list on screen.
        """
        with self._session() as session:
            return list(
                session.exec(
                    select(Meal)
                    .where(Meal.user_id == self._user_id)
                    .order_by(col(Meal.id))
                ).all()
            )

    def list_all_with_ingredients(
        self,
    ) -> list[tuple[Meal, list[tuple[MealIngredient, Ingredient]]]]:
        """Every meal with its ingredients, in two queries rather than one
        per meal - which would be a network round trip each in deployment."""
        with self._session() as session:
            meals = list(
                session.exec(
                    select(Meal)
                    .where(Meal.user_id == self._user_id)
                    .order_by(col(Meal.id))
                ).all()
            )

            rows = session.exec(
                select(MealIngredient, Ingredient)
                .join(Ingredient, col(Ingredient.id) == MealIngredient.ingredient_id)
                .join(Meal, col(Meal.id) == MealIngredient.meal_id)
                .where(Meal.user_id == self._user_id)
            ).all()

        by_meal: dict[int | None, list[tuple[MealIngredient, Ingredient]]] = {}
        for link, ingredient in rows:
            by_meal.setdefault(link.meal_id, []).append((link, ingredient))

        return [(meal, by_meal.get(meal.id, [])) for meal in meals]

    def get_with_ingredients(
        self, meal_id: int
    ) -> tuple[Meal, list[tuple[MealIngredient, Ingredient]]]:
        """One meal and its ingredients. Raises MealNotFoundError."""
        with self._session() as session:
            meal = self._get_or_raise(session, meal_id)
            return meal, self._ingredients_of(session, meal_id)

    def add(self, name: str, servings: int = 1) -> Meal:
        """Create a meal. Raises DuplicateNameError if the name is taken."""
        with self._session() as session:
            self._assert_name_available(session, name)
            meal = Meal(user_id=self._user_id, name=name, servings=servings)
            session.add(meal)
            session.flush()
            return meal

    def add_from_template(self, template: MealTemplate) -> Meal:
        """Create a meal and its template ingredients in one transaction."""
        with self._session() as session:
            self._assert_name_available(session, template.name)
            meal = Meal(
                user_id=self._user_id, name=template.name, servings=template.servings
            )
            session.add(meal)
            session.flush()

            for item in template.ingredients:
                self._attach_ingredient(
                    session, persisted_id(meal), item.name, item.qty, item.unit
                )
            return meal

    def update(self, meal_id: int, name: str, servings: int) -> None:
        """Rename a meal or change its serving size.

        Raises MealNotFoundError, or DuplicateNameError if the name is taken.
        """
        with self._session() as session:
            meal = self._get_or_raise(session, meal_id)
            if name.lower() != meal.name.lower():
                self._assert_name_available(session, name, exclude_id=meal_id)
            meal.name = name
            meal.servings = servings

    def delete(self, meal_id: int) -> None:
        """Delete a meal. Raises MealNotFoundError.

        Days it was planned on are cleared rather than deleted, servings
        included. Its ingredient lines go with it through the foreign key's
        `ON DELETE CASCADE`. (`ON DELETE SET NULL` on the plan's key would
        clear the meal too, but not the servings planned for it, so this
        clears both itself; the key remains the guarantee for any other
        writer.)
        """
        with self._session() as session:
            self._get_or_raise(session, meal_id)
            session.execute(
                update(WeeklyPlan)
                .where(
                    col(WeeklyPlan.user_id) == self._user_id,
                    col(WeeklyPlan.meal_id) == meal_id,
                )
                .values(meal_id=None, servings=None)
            )
            session.execute(
                delete(Meal).where(
                    col(Meal.id) == meal_id, col(Meal.user_id) == self._user_id
                )
            )

    # ------------------------------------------------------- ingredients

    def list_ingredients(self, meal_id: int) -> list[tuple[MealIngredient, Ingredient]]:
        """The (amount, ingredient) pairs attached to one of this user's meals.
        Empty for a meal that is not theirs."""
        with self._session() as session:
            if self._find_meal(session, meal_id) is None:
                return []
            return self._ingredients_of(session, meal_id)

    def add_ingredient(
        self, meal_id: int, ingredient_name: str, qty: float, unit: str
    ) -> None:
        """Attach an ingredient, creating it if new.

        Re-adding an existing one accumulates the quantity. Raises
        UnitMismatchError if the meal already uses a different unit, and
        MealNotFoundError if the meal does not exist or is not this user's.
        """
        with self._session() as session:
            self._get_or_raise(session, meal_id)
            self._attach_ingredient(session, meal_id, ingredient_name, qty, unit)

    def update_ingredient(
        self, meal_id: int, ingredient_id: int, qty: float, unit: str
    ) -> None:
        """Overwrite the quantity and unit of one ingredient on a meal.

        Raises IngredientNotOnMealError if it is not attached. Returning
        quietly instead would answer 200 to a request that changed nothing.
        """
        with self._session() as session:
            link = self._require_link(session, meal_id, ingredient_id)
            link.qty = qty
            link.unit = unit

    def remove_ingredient(self, meal_id: int, ingredient_id: int) -> None:
        """Detach an ingredient from a meal, leaving the ingredient itself.

        Raises IngredientNotOnMealError if it is not attached.
        """
        with self._session() as session:
            session.delete(self._require_link(session, meal_id, ingredient_id))

    # ----------------------------------------------------------- helpers

    def _find_meal(self, session: Session, meal_id: int) -> Meal | None:
        meal = session.get(Meal, meal_id)
        # Someone else's meal is indistinguishable from no meal at all.
        if meal is None or meal.user_id != self._user_id:
            return None
        return meal

    def _get_or_raise(self, session: Session, meal_id: int) -> Meal:
        meal = self._find_meal(session, meal_id)
        if meal is None:
            raise MealNotFoundError(f"No meal with id {meal_id}.")
        return meal

    @staticmethod
    def _ingredients_of(
        session: Session, meal_id: int
    ) -> list[tuple[MealIngredient, Ingredient]]:
        return list(
            session.exec(
                select(MealIngredient, Ingredient)
                .where(MealIngredient.meal_id == meal_id)
                .where(MealIngredient.ingredient_id == Ingredient.id)
            ).all()
        )

    def _assert_name_available(
        self, session: Session, name: str, *, exclude_id: int | None = None
    ) -> None:
        statement = select(Meal).where(
            Meal.user_id == self._user_id, func.lower(Meal.name) == name.lower()
        )
        if exclude_id is not None:
            statement = statement.where(Meal.id != exclude_id)
        existing = session.exec(statement).first()
        if existing:
            raise DuplicateNameError(f"A meal named '{existing.name}' already exists.")

    @staticmethod
    def _find_link(
        session: Session, meal_id: int, ingredient_id: int
    ) -> MealIngredient | None:
        return session.exec(
            select(MealIngredient).where(
                MealIngredient.meal_id == meal_id,
                MealIngredient.ingredient_id == ingredient_id,
            )
        ).first()

    def _require_link(
        self, session: Session, meal_id: int, ingredient_id: int
    ) -> MealIngredient:
        """The link, or a domain error naming which half is missing."""
        self._get_or_raise(session, meal_id)
        link = self._find_link(session, meal_id, ingredient_id)
        if link is None:
            raise IngredientNotOnMealError(
                f"Ingredient {ingredient_id} is not on meal {meal_id}."
            )
        return link

    def _find_ingredient_by_name(
        self, session: Session, name: str
    ) -> Ingredient | None:
        """This user's ingredient of that name, ignoring case, so "Eggs" and
        "eggs" are one item."""
        return session.exec(
            select(Ingredient).where(
                Ingredient.user_id == self._user_id,
                func.lower(Ingredient.name) == name.lower(),
            )
        ).first()

    def _attach_ingredient(
        self, session: Session, meal_id: int, name: str, qty: float, unit: str
    ) -> None:
        """Takes the caller's session so the operation stays in one
        transaction rather than opening a nested one."""
        ingredient = self._find_ingredient_by_name(session, name)
        if ingredient is None:
            ingredient = Ingredient(user_id=self._user_id, name=name)
            session.add(ingredient)
            session.flush()

        ingredient_id = persisted_id(ingredient)
        link = self._find_link(session, meal_id, ingredient_id)
        if link is None:
            session.add(
                MealIngredient(
                    meal_id=meal_id,
                    ingredient_id=ingredient_id,
                    qty=qty,
                    unit=unit,
                )
            )
            return

        if link.unit != unit:
            raise UnitMismatchError(
                f"{name} is already on this meal measured in '{link.unit}'. "
                f"Use the same unit to add more, or remove the existing entry first."
            )
        link.qty = link.qty + qty


class WeeklyPlanRepository(_Repository):
    """Reads and writes the meal assigned to each day of a given week."""

    def get_week(self, week_start_date: date) -> list[WeeklyPlan]:
        """Every stored day for one week. Days never set are absent."""
        with self._session() as session:
            statement = select(WeeklyPlan).where(
                WeeklyPlan.user_id == self._user_id,
                WeeklyPlan.week_start_date == week_start_date,
            )
            return list(session.exec(statement).all())

    def set_day(
        self,
        week_start_date: date,
        day: DayOfWeek | str,
        meal_id: int | None,
        servings: int | None = None,
    ) -> None:
        """Assign (or clear, with meal_id=None) the meal for one day."""
        self.set_week(week_start_date, {day: (meal_id, servings)})

    def set_week(
        self,
        week_start_date: date,
        assignments: dict[DayOfWeek | str, tuple[int | None, int | None]],
    ) -> None:
        """Assign several days of one week in a single transaction.

        `assignments` maps day -> (meal_id, servings); a None meal_id clears
        the day. A day at a time meant 14 statements and several seconds
        against a remote database.
        """
        if not assignments:
            return

        # Coerced rather than trusted: the column only holds weekday names,
        # and a clear domain error beats the check constraint's.
        wanted = {_as_day(day): value for day, value in assignments.items()}
        meal_ids = {meal_id for meal_id, _ in wanted.values() if meal_id is not None}

        with self._session() as session:
            # Only this user's meals. The foreign key would accept anyone's,
            # since a key check does not know who owns the row it points at.
            if meal_ids:
                found = set(
                    session.exec(
                        select(Meal.id).where(
                            col(Meal.id).in_(meal_ids), Meal.user_id == self._user_id
                        )
                    )
                )
                missing = sorted(meal_ids - found)
                if missing:
                    raise MealNotFoundError(f"No meal with id {missing[0]}.")

            # Replace rather than read-then-update: eight round trips for
            # a week becomes two. Row ids are referenced nowhere. Cleared
            # days keep a row with a NULL meal_id, distinguishing them from
            # days never set.
            session.execute(
                delete(WeeklyPlan).where(
                    col(WeeklyPlan.user_id) == self._user_id,
                    col(WeeklyPlan.week_start_date) == week_start_date,
                    col(WeeklyPlan.day_of_week).in_(wanted),
                )
            )
            # A Core insert becomes one executemany; adding ORM objects
            # would emit an INSERT per row to read back ids nothing uses.
            session.execute(
                insert(WeeklyPlan),
                [
                    {
                        "user_id": self._user_id,
                        "week_start_date": week_start_date,
                        "day_of_week": day,
                        "meal_id": meal_id,
                        "servings": servings,
                    }
                    for day, (meal_id, servings) in wanted.items()
                ],
            )

    def ingredient_rows_for_week(
        self, week_start_date: date
    ) -> list[tuple[str, float, str, int | None, int]]:
        """Every planned ingredient for a week: name, qty, unit, then the
        planned and recipe serving counts.

        One join rather than a query per meal and per ingredient, which cost
        48 statements for a full week - free on SQLite, ~2.4s over a network.

        SQLAlchemy's own select, because SQLModel's typed overloads stop at
        four columns and this needs five.
        """
        statement = (
            sa_select(
                col(Ingredient.name),
                col(MealIngredient.qty),
                col(MealIngredient.unit),
                col(WeeklyPlan.servings),
                col(Meal.servings),
            )
            .select_from(WeeklyPlan)
            .join(Meal, col(Meal.id) == col(WeeklyPlan.meal_id))
            .join(MealIngredient, col(MealIngredient.meal_id) == col(Meal.id))
            .join(Ingredient, col(Ingredient.id) == col(MealIngredient.ingredient_id))
            .where(
                col(WeeklyPlan.user_id) == self._user_id,
                col(WeeklyPlan.week_start_date) == week_start_date,
            )
        )
        with self._session() as session:
            return list(session.execute(statement).tuples().all())

    def copy_week(self, source_week: date, target_week: date) -> int:
        """Copy assigned days from one week onto another, returning the count.

        Unassigned source days are skipped rather than clearing the target.
        """
        copied = 0
        with self._session() as session:
            source_plans = session.exec(
                select(WeeklyPlan).where(
                    WeeklyPlan.user_id == self._user_id,
                    WeeklyPlan.week_start_date == source_week,
                )
            ).all()

            existing = {
                plan.day_of_week: plan
                for plan in session.exec(
                    select(WeeklyPlan).where(
                        WeeklyPlan.user_id == self._user_id,
                        WeeklyPlan.week_start_date == target_week,
                    )
                ).all()
            }

            for source in source_plans:
                if source.meal_id is None:
                    continue
                target = existing.get(source.day_of_week)
                if target:
                    target.meal_id = source.meal_id
                    target.servings = source.servings
                else:
                    session.add(
                        WeeklyPlan(
                            user_id=self._user_id,
                            week_start_date=target_week,
                            day_of_week=source.day_of_week,
                            meal_id=source.meal_id,
                            servings=source.servings,
                        )
                    )
                copied += 1
        return copied


class UserRepository:
    """Accounts. Not bound to a user, since its job is to find one."""

    def __init__(self, db: Database, session: Session | None = None) -> None:
        self._db = db
        self._session_override = session

    def _session(self) -> AbstractContextManager[Session]:
        if self._session_override is not None:
            return nullcontext(self._session_override)
        return self._db.session()

    def create(self, *, is_guest: bool = True) -> User:
        with self._session() as session:
            user = User(is_guest=is_guest)
            session.add(user)
            session.flush()
            return user

    def unclaimed_owner_id(self) -> int:
        """The account that owns the data from before accounts existed,
        created if there is none yet.

        TEMPORARY, until sessions land (Phase 1, step 4): until then every
        request acts as this account, so the app behaves exactly as the
        single-user app it was. It is removed when requests carry a session.
        """
        with self._session() as session:
            owner = session.exec(
                select(User)
                .where(
                    col(User.is_guest).is_(False),
                    col(User.email).is_(None),
                )
                .order_by(col(User.id))
            ).first()
            if owner is None:
                owner = User(is_guest=False)
                session.add(owner)
                session.flush()
            return persisted_id(owner)
