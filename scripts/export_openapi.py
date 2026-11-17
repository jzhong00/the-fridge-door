"""Write the API's OpenAPI document to docs/openapi.json.

The committed document is the contract between the API and the frontend:
the TypeScript types in web/src/api/schema.d.ts are generated from it, and
CI fails if either is out of date. So after changing a schema or a route:

    python scripts/export_openapi.py
    cd web && npm run generate:api

`--check` exits non-zero instead of writing, for CI and the test suite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "openapi.json"


def render() -> str:
    """The current document, formatted exactly as it is committed."""
    sys.path.insert(0, str(ROOT))
    from server.main import app

    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    current = render()
    if "--check" in argv:
        if not OUTPUT.exists() or OUTPUT.read_text() != current:
            print(
                f"{OUTPUT.relative_to(ROOT)} is out of date. "
                "Run: python scripts/export_openapi.py",
                file=sys.stderr,
            )
            return 1
        return 0
    OUTPUT.write_text(current)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
