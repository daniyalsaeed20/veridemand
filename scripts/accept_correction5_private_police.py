"""Opaque Correction 5 acceptance for private police dense-form OCR quality.

Records only safe aggregates. Never prints extracted text or private filenames.
Requires a running API at VERIDEMAND_API_BASE (default http://127.0.0.1:8000)
whose /health/live git_commit matches the current repository HEAD.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

from scripts.lib.api_process_guard import assert_api_matches_head

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
PRIV = ROOT / "fixtures" / "private"
PDF = PRIV / "private_scan_001.pdf"
OUT = ROOT / "temp" / "private_acceptance" / "correction5_police.json"
OPAQUE = "private_police_scan"


def _verify_build() -> dict[str, Any]:
    return assert_api_matches_head(BASE, root=ROOT)


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
    try:
        identity = _verify_build()
    except RuntimeError as exc:
        print(
            json.dumps(
                {
                    "opaque_label": OPAQUE,
                    "pass": False,
                    "error": "build_identity_mismatch",
                    "message": str(exc),
                }
            )
        )
        return 2

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
        doc = _wait_terminal(client, sid, doc_id, timeout=900.0)
        status = str(doc.get("status") or "")
        visual = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/summary")
        visual.raise_for_status()
        summary = visual.json()
        page_count = int(summary.get("document_pages_total") or summary.get("page_count") or 0)
        pages = summary.get("page_summaries") or []

        page_reports: list[dict[str, Any]] = []
        route_counts: dict[str, int] = {}
        overlay_ok = 0
        for page_row in pages:
            if not isinstance(page_row, dict):
                continue
            page_number = int(page_row.get("page_number") or 0)
            detail = client.get(
                f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/pages/{page_number}"
            )
            detail.raise_for_status()
            page = detail.json()
            state = str(page.get("page_result_state") or page.get("page_route") or "unknown")
            route_counts[state] = route_counts.get(state, 0) + 1
            words = int(page.get("word_count") or 0)
            lines = int(page.get("line_count") or 0)
            available = bool(page.get("visual_result_available"))
            if available and (words > 0 or lines > 0):
                overlay_ok += 1
            primary_q = page.get("primary_quality") or {}
            fallback_q = page.get("fallback_quality") or {}
            page_reports.append(
                {
                    "page_number": page_number,
                    "page_profile": page.get("page_profile"),
                    "selected_ocr_pass": page.get("selected_ocr_pass"),
                    "primary_quality_status": page.get("primary_quality_status"),
                    "fallback_used": bool(page.get("fallback_used")),
                    "fallback_reason_codes": page.get("fallback_reason_codes") or [],
                    "fallback_quality_status": page.get("fallback_quality_status"),
                    "line_count": lines,
                    "word_count": words,
                    "primary_fragmentation_score": primary_q.get("fragmentation_score"),
                    "fallback_fragmentation_score": fallback_q.get("fragmentation_score"),
                    "primary_mean_confidence": primary_q.get("mean_confidence"),
                    "fallback_mean_confidence": fallback_q.get("mean_confidence"),
                    "primary_limit_side": page.get("primary_limit_side"),
                    "fallback_limit_side": page.get("fallback_limit_side"),
                    "fallback_duration_ms": page.get("fallback_duration_ms"),
                    "duration_ms": page.get("duration_ms"),
                    "peak_rss_mb": page.get("peak_rss_mb"),
                    "handwriting_assessment": page.get("handwriting_assessment"),
                    "overlay_ok": available and (words > 0 or lines > 0),
                }
            )

        full_ocr = route_counts.get("full_visual_ocr", 0)
        ok = (
            status.startswith("visual_processing_")
            and page_count == 2
            and full_ocr == 2
            and overlay_ok == 2
            and all(p.get("handwriting_assessment") == "pending_phase_5" for p in page_reports)
            and all(p.get("primary_quality_status") is not None for p in page_reports)
        )
        report = {
            "opaque_label": OPAQUE,
            "pass": ok,
            "identity": identity,
            "document_status": status,
            "page_count": page_count,
            "route_counts": route_counts,
            "pages": page_reports,
            "overlay_pass": overlay_ok == 2,
            "total_duration_s": round(time.perf_counter() - started, 2),
            "worker_restart_count": None,
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"opaque_label": OPAQUE, "pass": ok, "out": str(OUT)}))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
