"""Deterministically generate the committed OpenAPI schema.

Builds the FastAPI application in-process (no server), renders its OpenAPI
document with recursively sorted keys, stable 2-space indentation, LF line
endings, and a single trailing newline, and writes it to
``docs/contracts/openapi.json``.

Usage:
    python scripts/generate_contracts.py            # write the schema
    python scripts/generate_contracts.py --check    # verify, no write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "docs" / "contracts" / "openapi.json"


def _sort_recursively(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sort_recursively(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_sort_recursively(item) for item in value]
    return value


def build_openapi() -> dict[str, Any]:
    """Build the OpenAPI document from the application factory."""

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from backend.app.main import create_app

    app = create_app()
    return app.openapi()


def render(schema: dict[str, Any]) -> bytes:
    """Render the schema to canonical, deterministic bytes (LF, trailing NL)."""

    ordered = _sort_recursively(schema)
    text = json.dumps(ordered, indent=2, ensure_ascii=False)
    return (text + "\n").encode("utf-8")


def write() -> Path:
    content = render(build_openapi())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(content)
    return OUTPUT_PATH


def check() -> int:
    expected = render(build_openapi())
    if not OUTPUT_PATH.exists():
        print(f"DRIFT: {OUTPUT_PATH} does not exist. Run 'pnpm contracts:generate'.")
        return 1
    actual = OUTPUT_PATH.read_bytes()
    if actual != expected:
        print(f"DRIFT: {OUTPUT_PATH} is out of date. Run 'pnpm contracts:generate'.")
        return 1
    print(f"OK: {OUTPUT_PATH} matches the generated OpenAPI schema.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or verify the OpenAPI contract.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the committed schema matches without writing.",
    )
    args = parser.parse_args(argv)

    if args.check:
        return check()

    path = write()
    print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
