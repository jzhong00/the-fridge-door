"""The committed OpenAPI document must match the running API.

docs/openapi.json is what the frontend's TypeScript types are generated
from. If a schema or route changes without re-exporting it, the frontend
would compile against a contract the API no longer honours, and the mistake
would only surface as `undefined` in the browser. This replaces a regex
comparison of field names, which could not see types or nullability.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_openapi.py"


def _exporter():
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_committed_openapi_document_is_current():
    exporter = _exporter()

    committed = exporter.OUTPUT.read_text() if exporter.OUTPUT.exists() else ""

    assert committed == exporter.render(), (
        "docs/openapi.json is out of date. Run: python scripts/export_openapi.py, "
        "then `npm run generate:api` in web/."
    )


def test_errors_are_documented_as_problem_details():
    """Every operation documents its errors as RFC 9457 problems, so the
    generated client types describe what the API actually returns."""
    from server.main import app

    spec = app.openapi()
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            default = operation["responses"].get("default", {})
            assert "application/problem+json" in default.get("content", {}), (
                f"{method.upper()} {path} does not document problem responses"
            )
            for code, response in operation["responses"].items():
                if code[0] in "45":
                    assert list(response["content"]) == ["application/problem+json"]
