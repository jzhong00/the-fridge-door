"""A test client for the API, signed in as a fresh guest by default.

Only use it inside a test: the autouse `db` fixture is what points the app
at a throwaway database. Outside one, the app falls back to `.env`.

The base URL is https because the session cookie is `Secure` (and
`__Host-`): the client, like a browser, will not send it over plain http.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from server.deps import reset_services_cache
from server.main import app

BASE_URL = "https://testserver"


@contextmanager
def api_client(
    *, as_guest: bool = True, raise_server_exceptions: bool = True
) -> Generator[TestClient]:
    reset_services_cache()
    with TestClient(
        app, base_url=BASE_URL, raise_server_exceptions=raise_server_exceptions
    ) as client:
        if as_guest:
            response = client.post("/api/auth/guest")
            assert response.status_code == 201, response.text
        yield client
    reset_services_cache()
