"""Rate limits for login, signup and guest sessions.

Revision ID: 20261117_0003
Revises: 20261117_0002
Create Date: 2026-11-17

What changes: one new table, `rate_limits`, holding recent attempts per
throttled subject (app/ratelimit.py). Subjects are keyed hashes, never
emails or IP addresses. Additive, so safe for code already running.

In Postgres the runtime role may read and write it. It belongs to no user,
so it has no row-level security policy, like `users` and `sessions`.

How the upgrade can fail: it cannot, short of the table already existing.
"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "20261117_0003"
down_revision = "20261117_0002"
branch_labels = None
depends_on = None

ROLE = "meal_planner_app"


def upgrade() -> None:
    op.create_table(
        "rate_limits",
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
        sa.Column("scope", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("scope", "subject", name=op.f("pk_rate_limits")),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON rate_limits TO {ROLE}")


def downgrade() -> None:
    # Dropping the table drops its grants with it.
    op.drop_table("rate_limits")
