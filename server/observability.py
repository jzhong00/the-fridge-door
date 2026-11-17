"""Request correlation and structured logging.

Every response carries an ``X-Request-ID``, every log line written while
serving that request carries the same id, and each request ends with one
``http_request_completed`` event. On Vercel the logs are JSON lines, which
its log search can filter by field; locally they are plain text.

The id is always generated here. A client-supplied ``X-Request-ID`` is
ignored: the id exists to correlate our own logs, and a caller who could set
it could make unrelated requests look related.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import IO, Any, Literal

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: The parent of every logger the application writes to.
LOGGER_NAME = "meal_planner"
LOG_FORMAT_ENV_VAR = "MEAL_PLANNER_LOG_FORMAT"
REQUEST_ID_HEADER = "x-request-id"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)

request_logger = logging.getLogger(f"{LOGGER_NAME}.http")


def current_request_id() -> str | None:
    """The id of the request being served, or None outside a request."""
    return _request_id.get()


class RequestContextMiddleware:
    """Assign a request id, return it, and log the request's completion.

    Pure ASGI rather than ``BaseHTTPMiddleware``, which runs the app in a
    separate task: a ``ContextVar`` set there would not be visible to the
    handlers. It must be the outermost middleware, so responses written by
    CORS or by the error handlers carry the id as well.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        token = _request_id.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            request_logger.info(
                "%s %s %s",
                scope["method"],
                getattr(route, "path", "unmatched"),
                status_code,
                extra={
                    "event": "http_request_completed",
                    "method": scope["method"],
                    # The template, never the concrete path: it carries ids,
                    # and aggregating by endpoint needs one value per route.
                    "route": getattr(route, "path", "unmatched"),
                    "status_code": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            _request_id.reset(token)


#: Attributes every LogRecord has. Anything else on a record came from
#: ``extra=`` and belongs in the JSON event.
_STANDARD_ATTRIBUTES = set(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "asctime",
    "taskName",
    "request_id",
}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with a stable set of top-level fields."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        entry.update(
            (key, value)
            for key, value in vars(record).items()
            if key not in _STANDARD_ATTRIBUTES
        )
        if record.exc_info:
            entry["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(entry, default=str)


def _default_format() -> Literal["json", "text"]:
    configured = os.getenv(LOG_FORMAT_ENV_VAR)
    if configured in ("json", "text"):
        return configured
    # JSON where something machine-reads the logs; text for a person.
    return "json" if os.getenv("VERCEL") else "text"


def configure_logging(
    *, stream: IO[str] | None = None, fmt: Literal["json", "text"] | None = None
) -> None:
    """Send the application's logs to `stream` (stderr by default).

    Safe to call again: it replaces the handler rather than adding a second.
    The application logger does not propagate to the root logger, so lines
    are never duplicated by whatever the host has attached there.
    """
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.addFilter(_RequestIdFilter())
    if (fmt or _default_format()) == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s [%(request_id)s] %(message)s")
        )

    logger = logging.getLogger(LOGGER_NAME)
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
