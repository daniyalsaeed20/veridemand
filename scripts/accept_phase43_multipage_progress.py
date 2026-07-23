"""Opaque Phase 4.3 multipage progress acceptance against a running backend.

Usage (second shell while `pnpm dev:backend` runs):

  set VERIDEMAND_ACCEPT_PDF=tmp/extraction-remediation/uploads/3936314.pdf
  uv run --group ocr python scripts/accept_phase43_multipage_progress.py

Never prints OCR text or private filenames beyond an opaque label.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
_raw_pdf = os.environ.get("VERIDEMAND_ACCEPT_PDF", "")
PDF = Path(_raw_pdf)
if _raw_pdf and not PDF.is_file():
    candidate = ROOT / _raw_pdf
    if candidate.is_file():
        PDF = candidate
OPAQUE = os.environ.get("VERIDEMAND_ACCEPT_LABEL", "private-two-page-A")


def main() -> int:
    if not PDF.is_file():
        print(f"FAIL: set VERIDEMAND_ACCEPT_PDF to an existing PDF (got {PDF!s})")
        return 2

    client = httpx.Client(base_url=BASE, timeout=30.0)
    ready = client.get("/health/ready")
    body = ready.json()
    if ready.status_code != 200 or body.get("status") != "ready":
        print(
            f"FAIL: health/ready status_code={ready.status_code} "
            f"status={body.get('status')!r}"
        )
        return 2

    session = client.post("/api/v1/sessions").json()
    sid = session["session_id"]
    with PDF.open("rb") as handle:
        upload = client.post(
            f"/api/v1/sessions/{sid}/documents",
            files={"files": (f"{OPAQUE}.pdf", handle, "application/pdf")},
        )
    upload.raise_for_status()
    doc_id = upload.json()["accepted"][0]["document_id"]
    client.post(
        f"/api/v1/sessions/{sid}/process", json={"document_ids": [doc_id]}
    ).raise_for_status()

    overalls: list[float] = []
    pages_seen: list[int] = []
    terminal = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < 600:
        listed = client.get(f"/api/v1/sessions/{sid}/documents")
        listed.raise_for_status()
        payload = listed.json()
        docs_list = payload.get("documents")
        if not isinstance(docs_list, list):
            print(f"FAIL: unexpected documents payload keys={list(payload)}")
            return 1
        docs = {d["document_id"]: d for d in docs_list}
        doc = docs[doc_id]
        pct = float(doc.get("progress_percent") or 0)
        overalls.append(pct)
        page = doc.get("active_page_number")
        if isinstance(page, int):
            pages_seen.append(page)
        status = doc["status"]
        if status.startswith("visual_processing_") or status in {"failed", "cancelled"}:
            terminal = doc
            break
        # While still on page 1 complete band, must stay below 65.
        completed = doc.get("pages_completed") or 0
        total = doc.get("pages_total") or 0
        if status == "visual_processing" and total >= 2 and completed == 1 and pct >= 65:
            print("FAIL: overall reached 65 after page 1 of 2")
            print(json.dumps({"opaque_label": OPAQUE, "progress_percent": pct}, indent=2))
            return 1
        time.sleep(1.0)
    else:
        print("FAIL: timed out waiting for terminal visual status")
        return 1

    assert terminal is not None
    # Monotonic overall (allow equal).
    for i in range(1, len(overalls)):
        if overalls[i] + 1e-6 < overalls[i - 1]:
            print(f"FAIL: overall regression {overalls[i - 1]} -> {overalls[i]}")
            return 1

    report = {
        "opaque_label": OPAQUE,
        "page_count": terminal.get("pages_total"),
        "pages_completed": terminal.get("pages_completed"),
        "final_status": terminal.get("status"),
        "final_progress_percent": terminal.get("progress_percent"),
        "visual_result_available": terminal.get("visual_result_available"),
        "worker_generation": terminal.get("worker_generation"),
        "max_overall_before_terminal": max(overalls[:-1]) if len(overalls) > 1 else None,
        "elapsed_seconds": terminal.get("document_elapsed_seconds")
        or terminal.get("elapsed_seconds"),
        "pass": terminal.get("status")
        in {
            "visual_processing_complete",
            "visual_processing_partial",
        }
        and int(terminal.get("progress_percent") or 0) == 65,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
