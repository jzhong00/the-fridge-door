"""Repositories as an API request uses them: one transaction per call.

In the application each request opens one transaction and hands the session
to the repositories (server/deps.py). Repository tests mostly want the same
thing per call: do something, then check what was committed. This wraps a
repository so every method call runs in its own `Database.transaction()`,
committed if the call returns and rolled back if it raises, exactly as one
request would be.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlmodel import Session

from app.db import Database


class PerRequest:
    """Proxy whose method calls each run in a fresh transaction."""

    def __init__(self, db: Database, build: Callable[[Session], Any]) -> None:
        self._db = db
        self._build = build

    def __getattr__(self, name: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            with self._db.transaction() as session:
                return getattr(self._build(session), name)(*args, **kwargs)

        return call
