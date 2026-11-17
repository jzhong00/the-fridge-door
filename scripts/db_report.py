"""Print a database's migration revision and row counts. Read-only.

For rehearsing a migration on a Neon branch before production: run it
before and after `alembic upgrade head`, and the counts should match table
for table (meal -> meals, weeklyplan -> weekly_plans, ...), plus one row in
`users` when there was data to own.

    MEAL_PLANNER_DB_URL='postgresql+psycopg://...' python scripts/db_report.py

Only counts are printed, never row contents, so the output is safe to share.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

#: Before the accounts migration, and after it.
TABLES = (
    "meal",
    "ingredient",
    "mealingredient",
    "weeklyplan",
    "users",
    "sessions",
    "meals",
    "ingredients",
    "meal_ingredients",
    "weekly_plans",
)


def main() -> int:
    url = os.getenv("MEAL_PLANNER_DB_URL")
    if not url:
        print(
            "MEAL_PLANNER_DB_URL is not set in this shell. Stop here: do not run "
            "alembic until this prints the database you mean. If you ran "
            "`export MEAL_PLANNER_DB_URL=...`, put the URL in single quotes; "
            "unquoted, the & in it makes the shell run the export in the "
            "background, where it is lost.",
            file=sys.stderr,
        )
        return 1

    engine = create_engine(url)
    print(f"database: {make_url(url).render_as_string(hide_password=True)}")
    existing = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        revision = (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if "alembic_version" in existing
            else None
        )
        print(f"revision: {revision or '(none)'}")
        for table in TABLES:
            if table in existing:
                count = connection.execute(
                    text(f"SELECT count(*) FROM {table}")
                ).scalar()
                print(f"  {table:<18} {count}")
        if "users" in existing:
            owners = connection.execute(
                text("SELECT count(*) FROM users WHERE NOT is_guest AND email IS NULL")
            ).scalar()
            print(f"  unclaimed owner accounts: {owners}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
