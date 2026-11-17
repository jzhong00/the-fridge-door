"""accounts and per-user ownership

Adds `users` and `sessions`, gives every meal, ingredient and plan an owner,
and brings the schema onto the conventions in docs/conventions.md: plural
table names, named constraints, invariants enforced by the database,
indexed foreign keys and server-set timestamps.

The four existing tables are rebuilt rather than altered in place: each new
table is created with its final shape, the rows are copied across, and the
old table is dropped. On Postgres all of it is one transaction. It works the
same way on SQLite, which cannot alter most constraints in place, and gives
every constraint its conventional name rather than one the database chose.

Existing rows all go to one new account with no email or password: the
"unclaimed owner". It is not a guest, so guest cleanup never removes it, and
it gains credentials through `python -m app.cli claim-account`. An empty
database (CI, a fresh install) gets no such account.

How the upgrade can fail, before changing anything: if a row would break a
new constraint - a non-positive quantity or servings, a day that is not a
weekday, or two meals or ingredients whose names differ only in case. The
error names what to fix. Rows pointing at something already deleted (SQLite
never enforced the foreign keys) are not errors: a plan for a deleted meal
becomes a cleared day, and an ingredient line for a deleted meal is dropped.

Downgrade restores the old tables and copies the rows back, discarding
ownership. It refuses once more than one account owns data, because the old
tables cannot hold two people's plans for the same day: past that point the
rollback is the Neon branch taken before upgrading.

Revision ID: 20261117_0001
Revises: d8c62df4218c
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = "20261117_0001"
down_revision: str | Sequence[str] | None = "d8c62df4218c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_DAY_LIST = ", ".join(f"'{day}'" for day in _DAYS)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def _scalar(sql: str, **params) -> int:
    return op.get_bind().execute(sa.text(sql), params).scalar_one()


def _refuse_rows_that_break_new_constraints() -> None:
    """Fail with the reason, before anything changes, if existing data
    would violate a constraint this migration adds."""
    problems: list[str] = []

    checks = {
        "meal ingredients with a missing or non-positive quantity": "SELECT count(*) FROM mealingredient WHERE qty IS NULL OR qty <= 0",
        "meals with fewer than one serving": "SELECT count(*) FROM meal WHERE servings < 1",
        "planned days with fewer than one serving": "SELECT count(*) FROM weeklyplan WHERE servings IS NOT NULL AND servings < 1",
        "planned days that are not a weekday": f"SELECT count(*) FROM weeklyplan WHERE day_of_week NOT IN ({_DAY_LIST})",
    }
    for description, sql in checks.items():
        count = _scalar(sql)
        if count:
            problems.append(f"{count} {description}")

    for table in ("meal", "ingredient"):
        rows = op.get_bind().execute(
            sa.text(
                f"SELECT lower(name) FROM {table} GROUP BY lower(name) "
                "HAVING count(*) > 1"
            )
        )
        clashes = [row[0] for row in rows]
        if clashes:
            problems.append(
                f"{table} names that differ only in case: {', '.join(sorted(clashes))}"
            )

    if problems:
        raise RuntimeError(
            "Cannot add accounts until this data is fixed: " + "; ".join(problems)
        )


def _reset_sequences(tables: Sequence[str]) -> None:
    """Rows were copied with their ids, so each serial sequence must restart
    after the highest one. SQLite needs nothing: it uses max(rowid) + 1."""
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in tables:
        op.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT max(id) FROM {table}), 0) + 1, false)"
        )


def upgrade() -> None:
    _refuse_rows_that_break_new_constraints()

    op.create_table(
        "users",
        *_timestamps(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("password_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_guest", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.CheckConstraint(
            "(email IS NULL) = (password_hash IS NULL)",
            name=op.f("ck_users_credentials_complete"),
        ),
        sa.CheckConstraint(
            "NOT is_guest OR email IS NULL", name=op.f("ck_users_guests_have_no_email")
        ),
    )
    op.create_index(
        "uq_users_lower_email", "users", [sa.text("lower(email)")], unique=True
    )

    op.create_table(
        "sessions",
        *_timestamps(),
        sa.Column("token_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_sessions")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    op.create_table(
        "meals",
        *_timestamps(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meals")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_meals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("servings >= 1", name=op.f("ck_meals_servings_positive")),
    )
    op.create_index(
        "uq_meals_user_id_lower_name",
        "meals",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "ingredients",
        *_timestamps(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredients")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ingredients_user_id_users"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_ingredients_user_id_lower_name",
        "ingredients",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )

    op.create_table(
        "meal_ingredients",
        *_timestamps(),
        sa.Column("meal_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False),
        sa.Column(
            "unit",
            sqlmodel.sql.sqltypes.AutoString(),
            server_default="",
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "meal_id", "ingredient_id", name=op.f("pk_meal_ingredients")
        ),
        sa.ForeignKeyConstraint(
            ["meal_id"],
            ["meals.id"],
            name=op.f("fk_meal_ingredients_meal_id_meals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_meal_ingredients_ingredient_id_ingredients"),
            # Checked at the end of the statement, so an account's cascade
            # can remove ingredients and lines in either order.
            ondelete="NO ACTION",
        ),
        sa.CheckConstraint("qty > 0", name=op.f("ck_meal_ingredients_qty_positive")),
    )
    op.create_index(
        "ix_meal_ingredients_ingredient_id", "meal_ingredients", ["ingredient_id"]
    )

    op.create_table(
        "weekly_plans",
        *_timestamps(),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("day_of_week", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("meal_id", sa.Integer(), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_weekly_plans")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_weekly_plans_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["meal_id"],
            ["meals.id"],
            name=op.f("fk_weekly_plans_meal_id_meals"),
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            f"day_of_week IN ({_DAY_LIST})",
            name=op.f("ck_weekly_plans_day_of_week_valid"),
        ),
        sa.CheckConstraint(
            "servings IS NULL OR servings >= 1",
            name=op.f("ck_weekly_plans_servings_positive"),
        ),
    )
    op.create_index("ix_weekly_plans_meal_id", "weekly_plans", ["meal_id"])
    op.create_index(
        "uq_weekly_plans_user_id_week_start_date_day_of_week",
        "weekly_plans",
        ["user_id", "week_start_date", "day_of_week"],
        unique=True,
    )

    # ------------------------------------------------- move the data across

    has_data = _scalar(
        "SELECT (SELECT count(*) FROM meal) + (SELECT count(*) FROM ingredient) "
        "+ (SELECT count(*) FROM weeklyplan)"
    )
    if has_data:
        users = sa.table("users", sa.column("id"), sa.column("is_guest"))
        owner_id = (
            op.get_bind()
            .execute(sa.insert(users).values(is_guest=False).returning(users.c.id))
            .scalar_one()
        )

        bind = op.get_bind()
        bind.execute(
            sa.text(
                "INSERT INTO meals (id, user_id, name, servings, created_at, updated_at) "
                "SELECT id, :owner, name, servings, created_at, created_at FROM meal"
            ),
            {"owner": owner_id},
        )
        bind.execute(
            sa.text(
                "INSERT INTO ingredients (id, user_id, name) "
                "SELECT id, :owner, name FROM ingredient"
            ),
            {"owner": owner_id},
        )
        # Lines for a meal or ingredient that no longer exists are orphans
        # with nothing to show them; they are not carried over.
        bind.execute(
            sa.text(
                "INSERT INTO meal_ingredients (meal_id, ingredient_id, qty, unit) "
                "SELECT mi.meal_id, mi.ingredient_id, mi.qty, COALESCE(mi.unit, '') "
                "FROM mealingredient mi "
                "JOIN meal m ON m.id = mi.meal_id "
                "JOIN ingredient i ON i.id = mi.ingredient_id"
            )
        )
        # A plan for a meal that no longer exists becomes a cleared day, which
        # is what deleting the meal would have done had the key been enforced.
        bind.execute(
            sa.text(
                "INSERT INTO weekly_plans "
                "(id, user_id, week_start_date, day_of_week, meal_id, servings) "
                "SELECT w.id, :owner, w.week_start_date, w.day_of_week, m.id, "
                "CASE WHEN m.id IS NULL THEN NULL ELSE w.servings END "
                "FROM weeklyplan w LEFT JOIN meal m ON m.id = w.meal_id"
            ),
            {"owner": owner_id},
        )

    # Children before parents, so no foreign key is left pointing at nothing.
    op.drop_index(op.f("ix_weeklyplan_week_start_date"), table_name="weeklyplan")
    op.drop_index(op.f("ix_weeklyplan_day_of_week"), table_name="weeklyplan")
    op.drop_table("weeklyplan")
    op.drop_table("mealingredient")
    op.drop_index(op.f("ix_meal_name"), table_name="meal")
    op.drop_table("meal")
    op.drop_index(op.f("ix_ingredient_name"), table_name="ingredient")
    op.drop_table("ingredient")

    _reset_sequences(["users", "meals", "ingredients", "weekly_plans"])


def downgrade() -> None:
    owners = _scalar(
        "SELECT count(*) FROM (SELECT user_id FROM meals UNION "
        "SELECT user_id FROM ingredients UNION SELECT user_id FROM weekly_plans) o"
    )
    if owners > 1:
        raise RuntimeError(
            f"{owners} accounts own data, and the pre-accounts schema can hold only "
            "one person's. Restore the Neon branch taken before upgrading instead."
        )

    # The original schema, exactly as d8c62df4218c created it.
    op.create_table(
        "ingredient",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ingredient_name"), "ingredient", ["name"], unique=False)
    op.create_table(
        "meal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_meal_name"), "meal", ["name"], unique=False)
    op.create_table(
        "mealingredient",
        sa.Column("meal_id", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=True),
        sa.Column("unit", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["ingredient_id"], ["ingredient.id"]),
        sa.ForeignKeyConstraint(["meal_id"], ["meal.id"]),
        sa.PrimaryKeyConstraint("meal_id", "ingredient_id"),
    )
    op.create_table(
        "weeklyplan",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("day_of_week", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("meal_id", sa.Integer(), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["meal_id"], ["meal.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "week_start_date", "day_of_week", name="uq_weeklyplan_week_day"
        ),
    )
    op.create_index(
        op.f("ix_weeklyplan_day_of_week"), "weeklyplan", ["day_of_week"], unique=False
    )
    op.create_index(
        op.f("ix_weeklyplan_week_start_date"),
        "weeklyplan",
        ["week_start_date"],
        unique=False,
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO meal (id, name, servings, created_at) "
            "SELECT id, name, servings, created_at FROM meals"
        )
    )
    bind.execute(
        sa.text("INSERT INTO ingredient (id, name) SELECT id, name FROM ingredients")
    )
    bind.execute(
        sa.text(
            "INSERT INTO mealingredient (meal_id, ingredient_id, qty, unit) "
            "SELECT meal_id, ingredient_id, qty, unit FROM meal_ingredients"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO weeklyplan (id, week_start_date, day_of_week, meal_id, servings) "
            "SELECT id, week_start_date, day_of_week, meal_id, servings FROM weekly_plans"
        )
    )

    op.drop_table("weekly_plans")
    op.drop_table("meal_ingredients")
    op.drop_table("ingredients")
    op.drop_table("meals")
    op.drop_table("sessions")
    op.drop_table("users")

    _reset_sequences(["meal", "ingredient", "weeklyplan"])
