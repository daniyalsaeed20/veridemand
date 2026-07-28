#!/usr/bin/env python3
"""Opaque Correction 3 acceptance for private_text_rich_097.

1) Routing-only audit (no full OCR)
2) Optional full HTTP process against a running API

Never prints extracted text or private filenames.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
PRIV = ROOT / "fixtures" / "private"
MANIFEST = PRIV / "phase45-routing.local.json"
OUT = ROOT / "temp" / "private_acceptance" / "correction3_text_rich.json"
OPAQUE = "private_text_rich_097"
EXPECTED_PAGES = 97


def _resolve_pdf() -> Path | None:
    if not MANIFEST.is_file():
        return None
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    relative: str | None = None
    if isinstance(data.get("documents"), dict):
        relative = data["documents"].get(OPAQUE)
    elif OPAQUE in data and isinstance(data[OPAQUE], str):
        relative = str(data[OPAQUE])
    if not relative:
        return None
    path = (PRIV / relative).resolve()
    if not path.is_file() or PRIV.resolve() not in path.parents:
        return None
    return path


def _routing_only() -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_private_routing_only.py"),
            "--label",
            OPAQUE,
            "--out",
            str(ROOT / "temp" / "private_acceptance" / "correction3_routing_only_final.json"),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "pass": False,
            "stage": "routing_only",
            "error": proc.stderr[-500:] or proc.stdout[-500:],
        }
    summary = json.loads(proc.stdout)
    return {"pass": bool(summary.get("pass")), "stage": "routing_only", "summary": summary}


def _full_http(pdf_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        health = client.get("/health")
        if health.status_code != 200:
            return {"pass": False, "stage": "http", "error": "api_unavailable"}
        session = client.post("/sessions").json()
        session_id = session["session_id"]
        with pdf_path.open("rb") as handle:
            upload = client.post(
                f"/sessions/{session_id}/documents",
                files={"file": (f"{OPAQUE}.pdf", handle, "application/pdf")},
            )
        if upload.status_code >= 400:
            return {"pass": False, "stage": "http", "error": "upload_failed"}
        doc_id = upload.json()["document_id"]
        client.post(f"/sessions/{session_id}/process")
        deadline = time.time() + float(os.environ.get("VERIDEMAND_ACCEPT_TIMEOUT", "3600"))
        routes: dict[str, int] = {}
        while time.time() < deadline:
            time.sleep(2.0)
            status = client.get(f"/sessions/{session_id}/documents/{doc_id}")
            if status.status_code >= 400:
                continue
            body = status.json()
            state = body.get("status") or body.get("document_status")
            if state in {"complete", "completed", "failed", "cancelled"}:
                visual = client.get(f"/sessions/{session_id}/documents/{doc_id}/visual")
                if visual.status_code == 200:
                    summary = visual.json()
                    for page in summary.get("page_summaries") or []:
                        route = page.get("page_route") or page.get("page_result_state") or "unknown"
                        routes[route] = routes.get(route, 0) + 1
                return {
                    "pass": state in {"complete", "completed"},
                    "stage": "http",
                    "document_status": state,
                    "route_totals": routes,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "page_count": EXPECTED_PAGES,
                    "label": OPAQUE,
                }
        return {"pass": False, "stage": "http", "error": "timeout"}


def main() -> int:
    pdf = _resolve_pdf()
    if pdf is None:
        print(json.dumps({"pass": False, "error": "fixture_missing", "label": OPAQUE}))
        return 2
    from pypdf import PdfReader

    page_count = len(PdfReader(str(pdf)).pages)
    if page_count != EXPECTED_PAGES:
        print(
            json.dumps(
                {
                    "pass": False,
                    "error": "page_count_mismatch",
                    "label": OPAQUE,
                    "page_count": page_count,
                    "expected": EXPECTED_PAGES,
                }
            )
        )
        return 2

    routing = _routing_only()
    result: dict[str, Any] = {
        "label": OPAQUE,
        "page_count": page_count,
        "routing_only": routing,
    }
    skip_http = os.environ.get("VERIDEMAND_CORRECTION3_ROUTING_ONLY", "").strip() in {"1", "true"}
    if not skip_http:
        result["http"] = _full_http(pdf)
    else:
        result["http"] = {"pass": True, "stage": "http", "skipped": True}

    result["pass"] = bool(routing.get("pass")) and bool(result["http"].get("pass"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Sanitised stdout only.
    print(
        json.dumps(
            {
                "pass": result["pass"],
                "label": OPAQUE,
                "page_count": page_count,
                "routing_route_totals": (routing.get("summary") or {}).get("route_totals"),
                "http_route_totals": result["http"].get("route_totals"),
                "out": str(OUT.as_posix()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
