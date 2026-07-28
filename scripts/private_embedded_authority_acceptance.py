"""Opaque private acceptance recorder for Correction 1.

Records only safe aggregates. Never logs extracted private text.

Manual workflow (local gitignored PDF):
1. Process the private document through the running app under an opaque label.
2. Fill the JSON fields below from the visual summary / route diagnostics.
3. Save under temp/ (gitignored).

This script only validates and pretty-prints an already-collected opaque record.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_KEYS = (
    "opaque_label",
    "page_count",
    "final_route_counts",
    "candidate_counts",
    "verified_counts",
    "full_ocr_counts",
    "overlay_availability",
    "safe_reason_code_counts",
    "duration_seconds",
    "pass",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate opaque Correction 1 acceptance JSON")
    parser.add_argument("record", type=Path, help="Path to opaque acceptance JSON")
    args = parser.parse_args()
    data = json.loads(args.record.read_text(encoding="utf-8"))
    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise SystemExit(f"missing keys: {missing}")
    if data.get("pass") is not True:
        raise SystemExit("record.pass must be true for acceptance")
    # Refuse any string values that look like transcript dumps.
    for key, value in data.items():
        if isinstance(value, str) and len(value) > 200:
            raise SystemExit(f"refusing long string field: {key}")
    print(json.dumps({k: data[k] for k in REQUIRED_KEYS}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
