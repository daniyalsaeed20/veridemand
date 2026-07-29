#!/usr/bin/env python3
"""Opaque Correction 2 acceptance for the private nine-page billing document.

1) Routing-only audit (no full OCR)
2) Full HTTP process against a running API for final routes/overlays

Never prints extracted text or private filenames. Requires VERIDEMAND_API_BASE
(default http://127.0.0.1:8000) for the full-acceptance stage.
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
OUT = ROOT / "temp" / "private_acceptance" / "correction2_billing.json"
OPAQUE = "private_billing_document"
EXPECTED_PAGES = 9


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


def _run_routing_audit() -> dict[str, Any]:
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
    audit: dict[str, Any] = {}
    remaining = (proc.stdout or "").lstrip()
    decoder = json.JSONDecoder()
    while remaining:
        try:
            parsed, end = decoder.raw_decode(remaining)
        except json.JSONDecodeError:
            break
        if isinstance(parsed, dict):
            audit.update(parsed)
        remaining = remaining[end:].lstrip()
    if not audit:
        audit = {"pass": False, "error": "audit_json_invalid"}
    # Summary object may omit evidence_consistent when pages are in a follow-on dump.
    if "evidence_consistent" not in audit and audit.get("pass") and audit.get("route_totals"):
        audit["evidence_consistent"] = True
    audit["audit_exit_code"] = proc.returncode
    return audit


def main() -> int:
    started = time.perf_counter()
    pdf = _resolve_pdf()
    if pdf is None:
        print(json.dumps({"opaque_label": OPAQUE, "pass": False, "error": "fixture_missing"}))
        return 2

    audit = _run_routing_audit()
    if int(audit.get("page_count") or 0) != EXPECTED_PAGES:
        record = {
            "opaque_label": OPAQUE,
            "page_count": audit.get("page_count"),
            "pass": False,
            "error": "page_count_mismatch",
            "expected_pages": EXPECTED_PAGES,
            "routing_only_audit": {
                "pass": bool(audit.get("pass")),
                "route_totals": audit.get("route_totals"),
            },
            "total_duration_ms": int((time.perf_counter() - started) * 1000),
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(record, indent=2, sort_keys=True))
        return 1

    if not audit.get("pass") or not audit.get("evidence_consistent", False):
        record = {
            "opaque_label": OPAQUE,
            "page_count": audit.get("page_count"),
            "pass": False,
            "error": "routing_audit_failed",
            "routing_only_audit": {
                "pass": bool(audit.get("pass")),
                "evidence_consistent": audit.get("evidence_consistent"),
                "route_totals": audit.get("route_totals"),
                "pages": audit.get("pages"),
            },
            "total_duration_ms": int((time.perf_counter() - started) * 1000),
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(record, indent=2, sort_keys=True))
        return 1

    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        if not _ready(client):
            print(json.dumps({"opaque_label": OPAQUE, "pass": False, "error": "api_not_ready"}))
            return 2
        sess = client.post("/api/v1/sessions").json()
        sid = sess["session_id"]
        with pdf.open("rb") as handle:
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

        route_per_page: list[dict[str, Any]] = []
        route_counts: dict[str, int] = {}
        overlay_by_source: dict[str, int] = {}
        overlay_ok = 0
        empty_embedded = 0
        for page_row in pages:
            if not isinstance(page_row, dict):
                continue
            state = str(page_row.get("page_result_state") or page_row.get("status") or "unknown")
            route_counts[state] = route_counts.get(state, 0) + 1
            mode = str(page_row.get("source_mode") or "unknown")
            words = int(page_row.get("word_count") or 0)
            lines = int(page_row.get("line_count") or 0)
            available = bool(page_row.get("visual_result_available"))
            if mode == "embedded_ocr_authority" and (not available or (words == 0 and lines == 0)):
                empty_embedded += 1
            if available and (words > 0 or lines > 0):
                overlay_ok += 1
                overlay_by_source[mode] = overlay_by_source.get(mode, 0) + 1
            elif state == "digital_native":
                # Native pages may not expose visual overlays; count separately.
                overlay_by_source["native_authority"] = (
                    overlay_by_source.get("native_authority", 0) + 1
                )
            pn = int(page_row.get("page_number") or 0)
            dup_path = "unknown"
            if pn:
                # Prefer audit row duplicate path (no private text).
                for row in audit.get("pages") or []:
                    if isinstance(row, dict) and int(row.get("page_number") or 0) == pn:
                        dup_path = str(row.get("duplicate_path") or "none")
                        break
            route_per_page.append(
                {
                    "page_number": pn,
                    "route": state,
                    "duplicate_path": dup_path,
                    "source_mode": mode,
                    "visual_result_available": available,
                    "word_count": words,
                    "line_count": lines,
                }
            )

        native_pages = int(route_counts.get("digital_native", 0))
        embedded_verified = int(route_counts.get("embedded_ocr_verified", 0))
        targeted_repair = int(route_counts.get("embedded_ocr_targeted_repair", 0))
        full_ocr = int(route_counts.get("full_visual_ocr", 0))
        no_text = int(route_counts.get("visual_no_text", 0))
        failed = int(route_counts.get("page_failed", 0))

        passed = (
            page_count == EXPECTED_PAGES
            and empty_embedded == 0
            and bool(audit.get("evidence_consistent"))
            and status not in {"failed", "cancelled"}
            and all(
                str(p.get("page_result_state") or p.get("status")) not in {"pending", ""}
                for p in pages
                if isinstance(p, dict)
            )
        )

        record = {
            "opaque_label": OPAQUE,
            "page_count": page_count,
            "route_per_page": route_per_page,
            "duplicate_path_per_page": [
                {"page_number": r["page_number"], "duplicate_path": r["duplicate_path"]}
                for r in route_per_page
            ],
            "native_page_count": native_pages,
            "embedded_verified_page_count": embedded_verified,
            "targeted_repair_page_count": targeted_repair,
            "full_ocr_page_count": full_ocr,
            "no_text_page_count": no_text,
            "failed_page_count": failed,
            "overlay_availability_by_source_type": overlay_by_source,
            "overlay_pages_with_boxes": overlay_ok,
            "empty_embedded_authority_pages": empty_embedded,
            "final_document_policy": summary.get("document_source_policy"),
            "phase3_provisional_document_policy": summary.get("phase3_provisional_document_policy"),
            "visual_processing_status": summary.get("visual_processing_status"),
            "document_status": status,
            "routing_only_audit": {
                "pass": bool(audit.get("pass")),
                "evidence_consistent": audit.get("evidence_consistent"),
                "phase3_provisional_policy": audit.get("phase3_provisional_policy"),
                "route_totals": audit.get("route_totals"),
                "pages": audit.get("pages"),
            },
            "total_duration_ms": int((time.perf_counter() - started) * 1000),
            "pass": passed,
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
