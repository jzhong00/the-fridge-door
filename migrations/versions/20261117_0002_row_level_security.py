"""Row-level security and the runtime role.

Revision ID: 20261117_0002
Revises: 20261117_0001
Create Date: 2026-11-17

What changes (Postgres only; SQLite has no roles or row security, so this is
a no-op there):

1. A role, `meal_planner_app`, for the web app to connect as. Created
   NOLOGIN and with no password: a migration must not contain a secret.
   Whoever deploys gives it one, once (`ALTER ROLE meal_planner_app LOGIN
   PASSWORD ...`), and points the app's MEAL_PLANNER_DB_URL at it. The
   owner role keeps running migrations and jobs.
2. That role may read and write rows in the app's tables and use their id
   sequences. Nothing else: no DDL, no `alembic_version`.
3. Row-level security on the four tables holding someone's data. The app
   declares whose request it is serving with
   `set_config('app.user_id', <id>, true)` inside each request's
   transaction, and the policies let the role see and write only that
   user's rows. When nothing is declared, `current_app_user_id()` is NULL
   and no row matches: a code path that forgets to declare a user sees
   nothing rather than everything.
4. The policies also check what a row points at: a plan can only name the
   same user's meal, and a meal line only the same user's meal and
   ingredient. Foreign keys check only that the row exists; these check
   whose it is, which the schema notes listed as unenforced until now.

`users` and `sessions` have no policies: signing in has to find a session
or an email before anyone is known. They are reached only through
app/auth.py.

The owner is not subject to these policies (row security is enabled, not
forced), so migrations, the purge job and the account-claim command can
work across users, as they must.

How the upgrade can fail: if `meal_planner_app` already exists as a
superuser or with BYPASSRLS, the policies would mean nothing for it, so the
upgrade refuses instead of pretending.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261117_0002"
down_revision = "20261117_0001"
branch_labels = None
depends_on = None

ROLE = "meal_planner_app"

#: Every table the role may use, with the policy that applies (None: no row
#: security; reached only by the auth code).
_CURRENT_USER = "current_app_user_id()"
_POLICIES: dict[str, tuple[str, str] | None] = {
    "users": None,
    "sessions": None,
    "meals": (f"user_id = {_CURRENT_USER}", f"user_id = {_CURRENT_USER}"),
    "ingredients": (f"user_id = {_CURRENT_USER}", f"user_id = {_CURRENT_USER}"),
    "weekly_plans": (
        f"user_id = {_CURRENT_USER}",
        f"user_id = {_CURRENT_USER} AND (meal_id IS NULL OR EXISTS ("
        "SELECT 1 FROM meals WHERE meals.id = weekly_plans.meal_id "
        f"AND meals.user_id = {_CURRENT_USER}))",
    ),
    "meal_ingredients": (
        "EXISTS (SELECT 1 FROM meals WHERE meals.id = meal_ingredients.meal_id "
        f"AND meals.user_id = {_CURRENT_USER})",
        "EXISTS (SELECT 1 FROM meals WHERE meals.id = meal_ingredients.meal_id "
        f"AND meals.user_id = {_CURRENT_USER}) AND EXISTS (SELECT 1 FROM "
        "ingredients WHERE ingredients.id = meal_ingredients.ingredient_id "
        f"AND ingredients.user_id = {_CURRENT_USER})",
    ),
}
_SEQUENCES = (
    "users_id_seq",
    "meals_id_seq",
    "ingredients_id_seq",
    "weekly_plans_id_seq",
)


def _postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _postgres():
        return

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
            END IF;
        END
        $$
        """
    )
    unsafe = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = :role"
            ),
            {"role": ROLE},
        )
        .scalar()
    )
    if unsafe:
        raise RuntimeError(
            f"Role {ROLE} is a superuser or has BYPASSRLS, so row-level security "
            f"would not apply to it. Run ALTER ROLE {ROLE} NOSUPERUSER NOBYPASSRLS "
            "as an administrator, then upgrade again."
        )

    # NULL, not an error, when the request has not declared a user: an
    # unset custom setting reads as '' once set_config has been used in the
    # session, or as missing (NULL with missing_ok) before that.
    op.execute(
        """
        CREATE FUNCTION current_app_user_id() RETURNS integer
        LANGUAGE sql STABLE
        AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::integer $$
        """
    )

    op.execute(f"GRANT USAGE ON SCHEMA public TO {ROLE}")
    op.execute(f"GRANT EXECUTE ON FUNCTION current_app_user_id() TO {ROLE}")
    for table, policy in _POLICIES.items():
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {ROLE}")
        if policy is None:
            continue
        using, check = policy
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_own_rows ON {table} FOR ALL TO {ROLE} "
            f"USING ({using}) WITH CHECK ({check})"
        )
    for sequence in _SEQUENCES:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {sequence} TO {ROLE}")


def downgrade() -> None:
    if not _postgres():
        return

    for sequence in _SEQUENCES:
        op.execute(f"REVOKE ALL ON SEQUENCE {sequence} FROM {ROLE}")
    for table, policy in _POLICIES.items():
        if policy is not None:
            op.execute(f"DROP POLICY {table}_own_rows ON {table}")
            op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {table} FROM {ROLE}")
    op.execute(f"REVOKE ALL ON FUNCTION current_app_user_id() FROM {ROLE}")
    op.execute("DROP FUNCTION current_app_user_id()")
    op.execute(f"REVOKE ALL ON SCHEMA public FROM {ROLE}")
    # The role itself stays: roles belong to the whole server, not to this
    # database, and it may hold a password and privileges elsewhere.
