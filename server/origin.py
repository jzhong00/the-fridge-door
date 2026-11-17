"""Refusing state-changing requests sent by other websites (CSRF).

The session cookie is `SameSite=Strict`, so a browser does not attach it to
a request another site starts, and such a request arrives signed out. This
is the second layer, for the cases that first one does not cover: a browser
that gets SameSite wrong, or the cookie settings changing one day.

Browsers send `Origin` on every POST, PUT, PATCH and DELETE, and, where
supported, `Sec-Fetch-Site`. Neither can be set by a web page. A request
whose Origin is not this app is refused. A request with no Origin at all is
not from a browser page (curl, a script), cannot carry someone else's
cookie, and is let through, unless `Sec-Fetch-Site` says it came from
another site.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import Request

from app import events
from app.exceptions import CrossSiteRequestError

#: Comma-separated extra origins allowed to call the API, beyond the app's
#: own. Also the CORS allow-list. Off Vercel it defaults to the Vite dev
#: server, whose proxy rewrites Host, so the dev page's Origin no longer
#: matches the API's own host.
TRUSTED_ORIGINS_ENV_VAR = "MEAL_PLANNER_CORS_ORIGINS"
_DEVELOPMENT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def trusted_origins() -> list[str]:
    default = "" if os.getenv("VERCEL") else _DEVELOPMENT_ORIGINS
    configured = os.getenv(TRUSTED_ORIGINS_ENV_VAR, default)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def reject_cross_site_writes(request: Request) -> None:
    """App-wide dependency: 403 for a write that another site sent."""
    if request.method in _SAFE_METHODS:
        return

    origin = request.headers.get("origin")
    if origin is None:
        if request.headers.get("sec-fetch-site") in {"cross-site", "same-site"}:
            _refuse()
        return

    # Same host as the request was sent to: the app's own page. "null"
    # (sandboxed frames, file:// pages) has no host and never matches.
    if urlsplit(origin).netloc == request.headers.get("host"):
        return
    if origin in trusted_origins():
        return
    _refuse()


def _refuse() -> None:
    # The origin is not logged: it is whatever the other site sent.
    events.record("cross_site_refused", outcome="refused")
    raise CrossSiteRequestError(
        "That request came from another website, so it was refused."
    )
