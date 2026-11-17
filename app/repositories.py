"""Data-access layer.

Every repository is bound to one user when it is constructed, and every
query it runs is scoped to that user. There is no method that takes a user
per call, so there is no method where forgetting it is possible: an unscoped
query is not expressible through this module. (Row-level security in
Postgres sits behind this, for the case where that reasoning is wrong.)

Asking for another user's row behaves exactly like asking for a row that
does not exist, so the API answers 404 either way and never confirms that
someone else's id is real.

Repositories never open, commit or roll back a transaction. They are handed
a session already inside one (`Database.transaction()`), and whoever opened
it decides the outcome: for the API, one transaction per request, so
everything a request does lands together or not at all. Sessions are made
with autobegin off, so a statement outside that transaction raises instead
of silently starting one that nobody commits.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, insert, update
from sqlalchemy import select as sa_select
from sqlalchemy.dialects import postgresql, sqlite
from sqlmodel import Session, col, select

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
    """The session to work in and the user every query is scoped to.

    Every write flushes before returning, so a constraint violation is
    raised by the method that caused it rather than later, at commit, where
    it could no longer be told apart from any other failure.
    """

    def __init__(self, session: Session, *, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    @property
    def user_id(self) -> int:
        return self._user_id


class IngredientRepository(_Repository):
    """Reads over one user's ingredients."""

    def list_all(self) -> list[Ingredient]:
        """Every ingredient this user has used, for the autocomplete."""
        return list(
            self._session.exec(
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
        return list(
            self._session.exec(
                select(Meal).where(Meal.user_id == self._user_id).order_by(col(Meal.id))
            ).all()
        )

    def list_all_with_ingredients(
        self,
    ) -> list[tuple[Meal, list[tuple[MealIngredient, Ingredient]]]]:
        """Every meal with its ingredients, in two queries rather than one
        per meal - which would be a network round trip each in deployment."""
        meals = self.list_all()
        rows = self._session.exec(
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
        meal = self._get_or_raise(meal_id)
        return meal, self._ingredients_of(meal_id)

    def add(self, name: str, servings: int = 1) -> Meal:
        """Create a meal. Raises DuplicateNameError if the name is taken."""
        self._assert_name_available(name)
        meal = Meal(user_id=self._user_id, name=name, servings=servings)
        self._session.add(meal)
        self._session.flush()
        return meal

    def add_from_template(self, template: MealTemplate) -> Meal:
        """Create a meal and its template ingredients.

        If an ingredient fails part-way, the error leaves the meal half-built
        inside the caller's transaction, and the caller's rollback removes it.
        """
        meal = self.add(template.name, template.servings)
        for item in template.ingredients:
            self._attach_ingredient(persisted_id(meal), item.name, item.qty, item.unit)
        return meal

    def update(self, meal_id: int, name: str, servings: int) -> None:
        """Rename a meal or change its serving size.

        Raises MealNotFoundError, or DuplicateNameError if the name is taken.
        """
        meal = self._get_or_raise(meal_id)
        if name.lower() != meal.name.lower():
            self._assert_name_available(name, exclude_id=meal_id)
        meal.name = name
        meal.servings = servings
        self._session.flush()

    def delete(self, meal_id: int) -> None:
        """Delete a meal. Raises MealNotFoundError.

        Days it was planned on are cleared rather than deleted, servings
        included. Its ingredient lines go with it through the foreign key's
        `ON DELETE CASCADE`. (`ON DELETE SET NULL` on the plan's key would
        clear the meal too, but not the servings planned for it, so this
        clears both itself; the key remains the guarantee for any other
        writer.)
        """
        self._get_or_raise(meal_id)
        self._session.execute(
            update(WeeklyPlan)
            .where(
                col(WeeklyPlan.user_id) == self._user_id,
                col(WeeklyPlan.meal_id) == meal_id,
            )
            .values(meal_id=None, servings=None)
        )
        self._session.execute(
            delete(Meal).where(
                col(Meal.id) == meal_id, col(Meal.user_id) == self._user_id
            )
        )

    # ------------------------------------------------------- ingredients

    def list_ingredients(self, meal_id: int) -> list[tuple[MealIngredient, Ingredient]]:
        """The (amount, ingredient) pairs attached to one of this user's meals.
        Empty for a meal that is not theirs."""
        if self._find_meal(meal_id) is None:
            return []
        return self._ingredients_of(meal_id)

    def add_ingredient(
        self, meal_id: int, ingredient_name: str, qty: float, unit: str
    ) -> None:
        """Attach an ingredient, creating it if new.

        Re-adding an existing one accumulates the quantity. Raises
        UnitMismatchError if the meal already uses a different unit, and
        MealNotFoundError if the meal does not exist or is not this user's.
        """
        self._get_or_raise(meal_id)
        self._attach_ingredient(meal_id, ingredient_name, qty, unit)

    def update_ingredient(
        self, meal_id: int, ingredient_id: int, qty: float, unit: str
    ) -> None:
        """Overwrite the quantity and unit of one ingredient on a meal.

        Raises IngredientNotOnMealError if it is not attached. Returning
        quietly instead would answer 200 to a request that changed nothing.
        """
        link = self._require_link(meal_id, ingredient_id)
        link.qty = qty
        link.unit = unit
        self._session.flush()

    def remove_ingredient(self, meal_id: int, ingredient_id: int) -> None:
        """Detach an ingredient from a meal, leaving the ingredient itself.

        Raises IngredientNotOnMealError if it is not attached.
        """
        self._session.delete(self._require_link(meal_id, ingredient_id))
        self._session.flush()

    # ----------------------------------------------------------- helpers

    def _find_meal(self, meal_id: int) -> Meal | None:
        meal = self._session.get(Meal, meal_id)
        # Someone else's meal is indistinguishable from no meal at all.
        if meal is None or meal.user_id != self._user_id:
            return None
        return meal

    def _get_or_raise(self, meal_id: int) -> Meal:
        meal = self._find_meal(meal_id)
        if meal is None:
            raise MealNotFoundError(f"No meal with id {meal_id}.")
        return meal

    def _ingredients_of(self, meal_id: int) -> list[tuple[MealIngredient, Ingredient]]:
        return list(
            self._session.exec(
                select(MealIngredient, Ingredient)
                .where(MealIngredient.meal_id == meal_id)
                .where(MealIngredient.ingredient_id == Ingredient.id)
            ).all()
        )

    def _assert_name_available(
        self, name: str, *, exclude_id: int | None = None
    ) -> None:
        statement = select(Meal).where(
            Meal.user_id == self._user_id, func.lower(Meal.name) == name.lower()
        )
        if exclude_id is not None:
            statement = statement.where(Meal.id != exclude_id)
        existing = self._session.exec(statement).first()
        if existing:
            raise DuplicateNameError(f"A meal named '{existing.name}' already exists.")

    def _find_link(self, meal_id: int, ingredient_id: int) -> MealIngredient | None:
        return self._session.exec(
            select(MealIngredient).where(
                MealIngredient.meal_id == meal_id,
                MealIngredient.ingredient_id == ingredient_id,
            )
        ).first()

    def _require_link(self, meal_id: int, ingredient_id: int) -> MealIngredient:
        """The link, or a domain error naming which half is missing."""
        self._get_or_raise(meal_id)
        link = self._find_link(meal_id, ingredient_id)
        if link is None:
            raise IngredientNotOnMealError(
                f"Ingredient {ingredient_id} is not on meal {meal_id}."
            )
        return link

    def _find_ingredient_by_name(self, name: str) -> Ingredient | None:
        """This user's ingredient of that name, ignoring case, so "Eggs" and
        "eggs" are one item."""
        return self._session.exec(
            select(Ingredient).where(
                Ingredient.user_id == self._user_id,
                func.lower(Ingredient.name) == name.lower(),
            )
        ).first()

    def _get_or_create_ingredient(self, name: str) -> Ingredient:
        """This user's ingredient of that name, created if it is new.

        Safe when two requests add the same new ingredient at once. A plain
        "look it up, insert it if missing" lets both see nothing and both
        insert; the unique index then rejects the second, and in Postgres
        that error poisons the rest of the transaction, so the whole request
        fails. `INSERT ... ON CONFLICT DO NOTHING` instead waits for the
        other insert, sees its row, and does nothing, and the lookup after it
        finds that row. The first lookup is only a shortcut: the ingredient
        usually exists already, and then one statement is enough.
        """
        existing = self._find_ingredient_by_name(name)
        if existing is not None:
            return existing

        dialect = self._session.get_bind().dialect.name
        upsert = postgresql.insert if dialect == "postgresql" else sqlite.insert
        self._session.execute(
            upsert(Ingredient)
            .values(user_id=self._user_id, name=name)
            .on_conflict_do_nothing(
                # The unique index `uq_ingredients_user_id_lower_name`.
                index_elements=[col(Ingredient.user_id), func.lower(Ingredient.name)]
            )
        )
        created = self._find_ingredient_by_name(name)
        if created is None:  # pragma: no cover - the insert or the conflict made it
            raise RuntimeError(f"Ingredient {name!r} vanished after its insert.")
        return created

    def _attach_ingredient(
        self, meal_id: int, name: str, qty: float, unit: str
    ) -> None:
        ingredient_id = persisted_id(self._get_or_create_ingredient(name))
        link = self._find_link(meal_id, ingredient_id)
        if link is None:
            self._session.add(
                MealIngredient(
                    meal_id=meal_id,
                    ingredient_id=ingredient_id,
                    qty=qty,
                    unit=unit,
                )
            )
            self._session.flush()
            return

        if link.unit != unit:
            raise UnitMismatchError(
                f"{name} is already on this meal measured in '{link.unit}'. "
                f"Use the same unit to add more, or remove the existing entry first."
            )
        link.qty = link.qty + qty
        self._session.flush()


class WeeklyPlanRepository(_Repository):
    """Reads and writes the meal assigned to each day of a given week."""

    def get_week(self, week_start_date: date) -> list[WeeklyPlan]:
        """Every stored day for one week. Days never set are absent."""
        statement = select(WeeklyPlan).where(
            WeeklyPlan.user_id == self._user_id,
            WeeklyPlan.week_start_date == week_start_date,
        )
        return list(self._session.exec(statement).all())

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
        """Assign several days of one week at once.

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

        # Only this user's meals. The foreign key would accept anyone's,
        # since a key check does not know who owns the row it points at.
        if meal_ids:
            found = set(
                self._session.exec(
                    select(Meal.id).where(
                        col(Meal.id).in_(meal_ids), Meal.user_id == self._user_id
                    )
                )
            )
            missing = sorted(meal_ids - found)
            if missing:
                raise MealNotFoundError(f"No meal with id {missing[0]}.")

        # Replace rather than read-then-update: eight round trips for a week
        # becomes two. Row ids are referenced nowhere. Cleared days keep a
        # row with a NULL meal_id, distinguishing them from days never set.
        self._session.execute(
            delete(WeeklyPlan).where(
                col(WeeklyPlan.user_id) == self._user_id,
                col(WeeklyPlan.week_start_date) == week_start_date,
                col(WeeklyPlan.day_of_week).in_(wanted),
            )
        )
        # A Core insert becomes one executemany; adding ORM objects would
        # emit an INSERT per row to read back ids nothing uses.
        self._session.execute(
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
        return list(self._session.execute(statement).tuples().all())

    def copy_week(self, source_week: date, target_week: date) -> int:
        """Copy assigned days from one week onto another, returning the count.

        Unassigned source days are skipped rather than clearing the target.
        """
        source_plans = self.get_week(source_week)
        existing = {plan.day_of_week: plan for plan in self.get_week(target_week)}

        copied = 0
        for source in source_plans:
            if source.meal_id is None:
                continue
            target = existing.get(source.day_of_week)
            if target:
                target.meal_id = source.meal_id
                target.servings = source.servings
            else:
                self._session.add(
                    WeeklyPlan(
                        user_id=self._user_id,
                        week_start_date=target_week,
                        day_of_week=source.day_of_week,
                        meal_id=source.meal_id,
                        servings=source.servings,
                    )
                )
            copied += 1
        self._session.flush()
        return copied


class UserRepository:
    """Accounts. Not bound to a user, since its job is to find one."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, is_guest: bool = True) -> User:
        user = User(is_guest=is_guest)
        self._session.add(user)
        self._session.flush()
        return user

    def unclaimed_owner_id(self) -> int:
        """The account that owns the data from before accounts existed,
        created if there is none yet.

        TEMPORARY, until sessions land (Phase 1, step 4): until then every
        request acts as this account, so the app behaves exactly as the
        single-user app it was. It is removed when requests carry a session.
        """
        owner = self._session.exec(
            select(User)
            .where(
                col(User.is_guest).is_(False),
                col(User.email).is_(None),
            )
            .order_by(col(User.id))
        ).first()
        if owner is None:
            owner = self.create(is_guest=False)
        return persisted_id(owner)
