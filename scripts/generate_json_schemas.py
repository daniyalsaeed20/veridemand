#!/usr/bin/env python3
"""Export Pydantic JSON Schema to contracts/generated/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.models.registry import ContractRegistry  # noqa: E402


def main() -> int:
    out_dir = ROOT / "contracts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    schemas = ContractRegistry().json_schemas()
    for name, schema in schemas.items():
        path = out_dir / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")
    # Index for FE tooling
    index = {name: f"{name}.schema.json" for name in sorted(schemas)}
    (out_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"exported {len(schemas)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
