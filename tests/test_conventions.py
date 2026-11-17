"""The schema follows the conventions in docs/conventions.md.

Reviewers forget; a test does not. Each check walks every table in the
metadata, so a new table or column is held to the rules the moment it is
added, and the failure names exactly what broke them.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, Table
from sqlmodel import SQLModel

from app import models  # noqa: F401  (registers every table)

TABLES: list[Table] = list(SQLModel.metadata.sorted_tables)


def _leading_columns(index: Index) -> str | None:
    first = next(iter(index.expressions), None)
    return getattr(first, "name", None)


def test_table_names_are_plural_snake_case():
    for table in TABLES:
        assert table.name == table.name.lower(), table.name
        assert table.name.endswith("s"), f"{table.name} should be plural"


def test_every_table_has_a_conventionally_named_primary_key():
    for table in TABLES:
        assert table.primary_key.columns, f"{table.name} has no primary key"
        assert table.primary_key.name == f"pk_{table.name}", table.name


def test_every_foreign_key_chooses_what_happens_on_delete():
    """Leaving ON DELETE unset is a decision nobody made, so it must be
    written out, even when the choice is NO ACTION."""
    for table in TABLES:
        for fk in table.foreign_key_constraints:
            assert fk.ondelete in {"CASCADE", "SET NULL", "RESTRICT", "NO ACTION"}, (
                f"{table.name}.{fk.column_keys} has no deliberate ON DELETE"
            )


def test_every_foreign_key_is_indexed():
    """Postgres does not index the referencing side of a foreign key, so
    every delete of a parent scans the child table without one. A primary
    key or index whose leading column is the key counts."""
    for table in TABLES:
        leading = {_leading_columns(index) for index in table.indexes}
        leading.add(next(iter(table.primary_key.columns)).name)
        for fk in table.foreign_key_constraints:
            (column,) = fk.column_keys
            assert column in leading, f"{table.name}.{column} is not indexed"


def test_every_constraint_and_index_has_a_conventional_name():
    prefixes = {
        ForeignKeyConstraint: "fk_",
        CheckConstraint: "ck_",
    }
    for table in TABLES:
        for constraint in table.constraints:
            prefix = prefixes.get(type(constraint))
            if prefix:
                assert str(constraint.name).startswith(f"{prefix}{table.name}_"), (
                    f"{table.name}: {constraint.name}"
                )
        for index in table.indexes:
            expected = "uq_" if index.unique else "ix_"
            assert str(index.name).startswith(f"{expected}{table.name}_"), (
                f"{table.name}: {index.name}"
            )


def test_every_table_records_when_rows_were_created_and_changed():
    for table in TABLES:
        for name in ("created_at", "updated_at"):
            column = table.columns.get(name)
            assert column is not None, f"{table.name} has no {name}"
            assert column.server_default is not None, f"{table.name}.{name}"
            assert not column.nullable, f"{table.name}.{name}"
        assert table.columns["updated_at"].onupdate is not None, table.name


def test_every_timestamp_is_timezone_aware():
    """A naive column on Postgres silently drops the UTC offset."""
    for table in TABLES:
        for column in table.columns:
            if isinstance(column.type, DateTime):
                assert column.type.timezone, f"{table.name}.{column.name}"
