"""Shared dependencies: the database and the repositories over it."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.db import Database, load_env_file
from app.repositories import (
    IngredientRepository,
    MealRepository,
    UserRepository,
    WeeklyPlanRepository,
)


@dataclass(frozen=True, slots=True)
class Services:
    """Everything a route handler needs to read or change data."""

    meals: MealRepository
    ingredients: IngredientRepository
    plans: WeeklyPlanRepository


@lru_cache(maxsize=1)
def get_database() -> Database:
    """The process-wide Database. One engine, so the pool is actually reused.

    Establishing a connection costs several network round trips - far more
    than a query - so rebuilding the pool per request would dominate every
    response time.
    """
    load_env_file()
    return Database()


def get_services() -> Generator[Services]:
    """FastAPI dependency: one transaction per request, and the repositories
    that work inside it.

    Everything a request does commits together or not at all. A route that
    raises (a domain error included) rolls back whatever it had written,
    and one BEGIN/COMMIT per request rather than per repository saved about
    1.5 s of a 3.4 s week change against a database a network away.
    """
    with get_database().transaction() as session:
        # TEMPORARY (Phase 1, step 4 replaces it with the session's user):
        # every request acts as the account that owns the pre-accounts data,
        # so the app behaves as the single-user app it was until then.
        user_id = UserRepository(session).unclaimed_owner_id()
        yield Services(
            meals=MealRepository(session, user_id=user_id),
            ingredients=IngredientRepository(session, user_id=user_id),
            plans=WeeklyPlanRepository(session, user_id=user_id),
        )


#: What route handlers annotate their `services` parameter with.
#:
#: `scope="function"` makes the transaction commit when the route returns,
#: before the response is sent. FastAPI's default scope finishes yield
#: dependencies after the response has gone out, so a commit that failed
#: there (a dropped connection, a constraint checked at commit) would
#: already have told the client 200 for a write that never happened.
#: tests/test_transactions.py proves the difference.
#:
#: Annotated rather than a `Depends()` default, which FastAPI still accepts
#: but which evaluates a call at import time and reads as a mutable default.
ServicesDep = Annotated[Services, Depends(get_services, scope="function")]


def reset_services_cache() -> None:
    """Drop the cached engine. Used by tests between cases."""
    get_database.cache_clear()
