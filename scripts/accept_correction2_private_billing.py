#!/usr/bin/env python3
"""Opaque Correction 2 acceptance for the private nine-page billing document.

Runs routing-only audit first (no full OCR), then optionally records that the
audit passed. Never prints private text, filenames, or local absolute paths.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "temp" / "private_acceptance" / "correction2_billing.json"
OPAQUE = "private_billing_digital"


def main() -> int:
    started = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_billing_routing_only.py"),
            "--label",
            OPAQUE,
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        audit = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        audit = {"pass": False, "error": "audit_json_invalid"}

    pages = audit.get("pages") if isinstance(audit.get("pages"), list) else []
    route_counts: dict[str, int] = {}
    dup_paths: dict[str, int] = {}
    dup_hard = 0
    for row in pages:
        if not isinstance(row, dict):
            continue
        route = str(row.get("proposed_phase4_route") or "unknown")
        route_counts[route] = route_counts.get(route, 0) + 1
        path = str(row.get("duplicate_path") or "none")
        dup_paths[path] = dup_paths.get(path, 0) + 1
        if row.get("duplicate_hard_rejection"):
            dup_hard += 1

    record = {
        "opaque_label": OPAQUE,
        "page_count": audit.get("page_count"),
        "final_route_per_page": [
            {
                "page_number": r.get("page_number"),
                "route": r.get("proposed_phase4_route"),
                "duplicate_path": r.get("duplicate_path"),
            }
            for r in pages
            if isinstance(r, dict)
        ],
        "duplicate_path_counts": dup_paths,
        "duplicate_hard_rejection_count": dup_hard,
        "native_pages": route_counts.get("digital_native", 0),
        "embedded_verified_pages": route_counts.get("embedded_ocr_candidate", 0),
        "targeted_repair_pages": 0,
        "full_ocr_pages": route_counts.get("full_visual_ocr", 0),
        "overlay_availability": "routing_only_audit",
        "total_duration_ms": int((time.perf_counter() - started) * 1000),
        "pass": bool(audit.get("pass")) and proc.returncode == 0,
        "phase3_provisional_policy": audit.get("phase3_provisional_policy"),
        "reason_distribution": audit.get("reason_distribution"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if record["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
