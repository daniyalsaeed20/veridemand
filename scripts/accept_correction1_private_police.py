"""Opaque Correction 1 acceptance for the private police-style scan.

Records only safe aggregates. Never prints extracted text or private filenames.
Requires a running API at VERIDEMAND_API_BASE (default http://127.0.0.1:8000).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
PRIV = ROOT / "fixtures" / "private"
PDF = PRIV / "private_scan_001.pdf"
OUT = ROOT / "temp" / "private_acceptance" / "correction1_police.json"
OPAQUE = "private_police_scan"


def _ready(client: httpx.Client) -> bool:
    try:
        r = client.get("/health/ready", timeout=5.0)
        return r.status_code == 200 and r.json().get("status") == "ready"
    except Exception:
        return False


def _wait_terminal(client: httpx.Client, sid: str, doc_id: str, timeout: float) -> dict[str, Any]:
    t0 = time.monotonic()
    last: dict[str, Any] = {}
    while time.monotonic() - t0 < timeout:
        listed = client.get(f"/api/v1/sessions/{sid}")
        if listed.status_code != 200:
            time.sleep(2.0)
            continue
        docs = {d["document_id"]: d for d in listed.json().get("documents") or []}
        last = docs.get(doc_id) or {}
        status = str(last.get("status") or "")
        if status.startswith("visual_processing_") or status in {"failed", "cancelled"}:
            return last
        time.sleep(2.0)
    return last


def main() -> int:
    if not PDF.is_file():
        print(json.dumps({"opaque_label": OPAQUE, "pass": False, "error": "missing_private_pdf"}))
        return 2

    started = time.perf_counter()
    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        if not _ready(client):
            print(json.dumps({"opaque_label": OPAQUE, "pass": False, "error": "api_not_ready"}))
            return 2
        sess = client.post("/api/v1/sessions").json()
        sid = sess["session_id"]
        with PDF.open("rb") as handle:
            up = client.post(
                f"/api/v1/sessions/{sid}/documents",
                files={"files": (f"{OPAQUE}.pdf", handle, "application/pdf")},
            )
        up.raise_for_status()
        accepted = up.json().get("accepted") or []
        if not accepted:
            print(json.dumps({"opaque_label": OPAQUE, "pass": False, "error": "upload_rejected"}))
            return 1
        doc_id = accepted[0]["document_id"]
        client.post(
            f"/api/v1/sessions/{sid}/process",
            json={"document_ids": [doc_id]},
        ).raise_for_status()
        doc = _wait_terminal(client, sid, doc_id, timeout=600.0)
        status = str(doc.get("status") or "")
        visual = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/summary")
        visual.raise_for_status()
        summary = visual.json()
        page_count = int(summary.get("document_pages_total") or summary.get("page_count") or 0)
        pages = summary.get("page_summaries") or []
        route_counts: dict[str, int] = {}
        overlay_ok = 0
        empty_embedded = 0
        reason_counts: dict[str, int] = {}
        for page_row in pages:
            if not isinstance(page_row, dict):
                continue
            state = str(page_row.get("page_result_state") or page_row.get("status") or "unknown")
            route_counts[state] = route_counts.get(state, 0) + 1
            words = int(page_row.get("word_count") or 0)
            lines = int(page_row.get("line_count") or 0)
            available = bool(page_row.get("visual_result_available"))
            mode = str(page_row.get("source_mode") or "")
            if mode == "embedded_ocr_authority" and (not available or (words == 0 and lines == 0)):
                empty_embedded += 1
            if available and (words > 0 or lines > 0):
                overlay_ok += 1
            # Fetch page for reason codes only (aggregates).
            pn = int(page_row.get("page_number") or 0)
            if pn:
                pr = client.get(
                    f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/pages/{pn}",
                    params={"include_lines": "false", "include_words": "false"},
                )
                if pr.status_code == 200:
                    for code in pr.json().get("route_reason_codes") or []:
                        if isinstance(code, str) and len(code) < 80:
                            reason_counts[code] = reason_counts.get(code, 0) + 1

        visual_status = str(summary.get("visual_processing_status") or "")
        policy = str(summary.get("document_source_policy") or "")
        passed = (
            empty_embedded == 0
            and visual_status != "not_required"
            and page_count >= 2
            and all(
                str(p.get("page_result_state") or p.get("status")) not in {"pending", ""}
                for p in pages
                if isinstance(p, dict)
            )
            and (
                int(summary.get("full_ocr_pages_selected") or summary.get("full_ocr_pages") or 0)
                > 0
                or int(summary.get("embedded_pages_verified") or 0) > 0
            )
        )
        record = {
            "opaque_label": OPAQUE,
            "page_count": page_count,
            "final_route_counts": route_counts,
            "candidate_counts": {
                "note": "candidate geometry retained on disk; not exposed in public summary"
            },
            "verified_counts": {
                "embedded_pages_verified": int(
                    summary.get("embedded_pages_verified")
                    or summary.get("embedded_ocr_pages_verified")
                    or 0
                ),
            },
            "full_ocr_counts": {
                "selected": int(
                    summary.get("full_ocr_pages_selected") or summary.get("full_ocr_pages") or 0
                ),
                "completed": int(summary.get("full_ocr_pages_completed") or 0),
            },
            "overlay_availability": {
                "pages_with_boxes": overlay_ok,
                "empty_embedded_authority_pages": empty_embedded,
            },
            "safe_reason_code_counts": reason_counts,
            "visual_processing_status": visual_status,
            "document_source_policy": policy,
            "phase3_provisional_document_policy": summary.get("phase3_provisional_document_policy"),
            "document_status": status,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "pass": passed,
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"opaque_label": OPAQUE, "pass": passed, "out": str(OUT.name)}))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
