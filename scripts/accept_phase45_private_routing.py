"""Phase 4.5 private corpus routing acceptance (opaque labels only).

Reads gitignored ``fixtures/private/phase45-routing.local.json`` mapping
opaque labels to local filenames under ``fixtures/private/``.

Never prints OCR/native text, private source filenames, or absolute paths.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
PRIV = ROOT / "fixtures" / "private"
MANIFEST = PRIV / "phase45-routing.local.json"
OUT_DIR = ROOT / "tmp" / "phase45-acceptance"

REQUIRED_LABELS = (
    "private_police_scan",
    "private_billing_digital",
    "private_medical_embedded_ocr",
)

BANNED_TOKENS = (
    "AMINI",
    "wellstar",
    "srmc",
    "MR 040926",
    "JACKMAN",
    "MEDICAL RECORDS",
)


def _ready(client: httpx.Client) -> bool:
    try:
        r = client.get("/health/ready", timeout=5.0)
        if r.status_code != 200:
            return False
        return bool(r.json().get("status") == "ready")
    except Exception:
        return False


def _wait_terminal(client: httpx.Client, sid: str, doc_id: str, timeout: float) -> dict[str, Any]:
    t0 = time.monotonic()
    last: dict[str, Any] = {}
    terminal_prefixes = ("visual_processing_",)
    terminal_exact = {"failed", "cancelled"}
    seen_ok = False
    missing_streak = 0
    while time.monotonic() - t0 < timeout:
        listed = client.get(f"/api/v1/sessions/{sid}")
        if listed.status_code == 404:
            missing_streak += 1
            if seen_ok and missing_streak >= 3:
                return {"status": "failed", "failure_code": "session_lost"}
            time.sleep(2.0)
            continue
        missing_streak = 0
        listed.raise_for_status()
        seen_ok = True
        payload = listed.json()
        docs_list = payload.get("documents")
        if not isinstance(docs_list, list):
            docs_list = []
        docs = {d["document_id"]: d for d in docs_list}
        last = docs.get(doc_id) or {}
        status = str(last.get("status") or "")
        if status.startswith(terminal_prefixes) or status in terminal_exact:
            return last
        time.sleep(2.0)
    return last


def _route_counts_from_visual(summary: dict[str, Any]) -> dict[str, int]:
    counts = {
        "digital_native": 0,
        "embedded_ocr_verified": 0,
        "embedded_ocr_targeted_repair": 0,
        "full_visual_ocr": 0,
        "visual_no_text": 0,
        "page_failed": 0,
        "page_cancelled": 0,
        "unknown": 0,
    }
    hist = summary.get("final_route_histogram")
    if isinstance(hist, dict):
        mapping = (
            ("digital_native", "digital_native_pages"),
            ("embedded_ocr_verified", "embedded_ocr_verified_pages"),
            ("embedded_ocr_targeted_repair", "embedded_ocr_targeted_repair_pages"),
            ("full_visual_ocr", "full_visual_ocr_pages"),
            ("visual_no_text", "visual_no_text_pages"),
            ("page_failed", "page_failed_pages"),
        )
        for out_key, hist_key in mapping:
            counts[out_key] = int(hist.get(hist_key) or hist.get(out_key) or 0)
        counts["page_cancelled"] = int(
            hist.get("page_cancelled_pages") or hist.get("page_cancelled") or 0
        )
        return counts
    pages = summary.get("page_summaries")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            route = str(page.get("page_result_state") or page.get("page_route") or "")
            if route in counts:
                counts[route] += 1
            elif route == "cancelled":
                counts["page_cancelled"] += 1
            elif page.get("native_retained") and not page.get("page_result_state"):
                # native_retained alone is not exclusive digital_native when embedded
                # may also set the flag; prefer unknown over double-counting.
                counts["unknown"] += 1
            elif str(page.get("status") or "") in {
                "no_text",
                "visual_no_text",
                "completed_no_text",
            }:
                counts["visual_no_text"] += 1
            else:
                counts["unknown"] += 1
    # Do not map native_pages_retained → digital_native (overlapping diagnostic).
    return counts


def _process_one(
    client: httpx.Client,
    label: str,
    path: Path,
    timeout: float,
) -> dict[str, Any]:
    t0 = time.monotonic()
    session = client.post("/api/v1/sessions").json()
    sid = session["session_id"]
    upload_name = f"{label}.pdf"
    with path.open("rb") as handle:
        upload = client.post(
            f"/api/v1/sessions/{sid}/documents",
            files={"files": (upload_name, handle, "application/pdf")},
        )
    upload.raise_for_status()
    body = upload.json()
    accepted = body.get("accepted") or []
    if not accepted:
        return {
            "label": label,
            "pass": False,
            "error": "upload_rejected",
            "duration_seconds": round(time.monotonic() - t0, 1),
        }
    doc_id = accepted[0]["document_id"]
    client.post(
        f"/api/v1/sessions/{sid}/process",
        json={"document_ids": [doc_id]},
    ).raise_for_status()
    terminal = _wait_terminal(client, sid, doc_id, timeout)
    visual = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/summary")
    native = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/native/summary")
    canon = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/canonical")
    visual_body: dict[str, Any] = {}
    if visual.status_code == 200:
        visual_body = visual.json()
    routes = _route_counts_from_visual(visual_body)
    status = str(terminal.get("status") or "")
    record: dict[str, Any] = {
        "label": label,
        "page_count": terminal.get("page_count") or visual_body.get("page_count"),
        "document_status": status,
        "visual_processing_status": visual_body.get("visual_processing_status"),
        "document_source_policy": terminal.get("document_source_policy")
        or visual_body.get("document_source_policy"),
        "progress_percent": terminal.get("progress_percent"),
        "canonical_view_available": bool(terminal.get("canonical_view_available")),
        "canonical_status": canon.status_code,
        "visual_summary_status": visual.status_code,
        "native_summary_status": native.status_code,
        "handwriting_assessment_pending": bool(
            visual_body.get("handwriting_assessment_pending", True)
        ),
        "route_counts": routes,
        "native_pages_retained": visual_body.get("native_pages_retained"),
        "embedded_ocr_pages_verified": visual_body.get("embedded_ocr_pages_verified"),
        "targeted_repair_pages": visual_body.get("targeted_repair_pages"),
        "full_ocr_pages": visual_body.get("full_ocr_pages"),
        "visual_no_text_pages": visual_body.get("visual_no_text_pages"),
        "pages_selected": visual_body.get("pages_selected"),
        "pages_completed": visual_body.get("pages_completed"),
        "pages_failed": visual_body.get("pages_failed"),
        "average_full_ocr_page_seconds": terminal.get("average_full_ocr_page_seconds"),
        "pages_per_minute": terminal.get("pages_per_minute"),
        "duration_seconds": round(time.monotonic() - t0, 1),
        "pass": False,
    }
    ok_terminal = status.startswith("visual_processing_")
    ok_http = visual.status_code == 200 and canon.status_code == 200
    ok_hw = record["handwriting_assessment_pending"] is True
    ok_cap = int(terminal.get("progress_percent") or 0) <= 65
    record["pass"] = bool(ok_terminal and ok_http and ok_hw and ok_cap)
    return record


def _load_manifest() -> dict[str, str]:
    if not MANIFEST.is_file():
        raise SystemExit(
            f"FAIL: missing manifest {MANIFEST.as_posix()} "
            "(copy from phase45-routing.local.json.example)"
        )
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    docs = data.get("documents") if isinstance(data, dict) else None
    if not isinstance(docs, dict):
        raise SystemExit("FAIL: manifest.documents must be an object of label -> relative filename")
    mapping: dict[str, str] = {}
    for label in REQUIRED_LABELS:
        rel = docs.get(label)
        if not isinstance(rel, str) or not rel.strip():
            raise SystemExit(f"FAIL: manifest missing entry for {label}")
        mapping[label] = rel.strip()
    return mapping


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mapping = _load_manifest()
    subset_only = os.environ.get("VERIDEMAND_PHASE45_SUBSET", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    labels = ("private_police_scan", "private_billing_digital") if subset_only else REQUIRED_LABELS

    client = httpx.Client(base_url=BASE, timeout=120.0)
    if not _ready(client):
        print("FAIL: /health/ready not ready — start backend (pnpm dev / uvicorn)")
        return 2

    results: list[dict[str, Any]] = []
    overall_pass = True
    for label in labels:
        rel = mapping[label]
        path = (PRIV / rel).resolve()
        try:
            path.relative_to(PRIV.resolve())
        except ValueError:
            print(f"FAIL: {label} path escapes private root")
            return 1
        if not path.is_file():
            print(f"FAIL: missing file for opaque label {label}")
            return 2
        # Timeout: police/billing ~15m; medical 104p allow up to 3h.
        timeout = 10800.0 if label == "private_medical_embedded_ocr" else 900.0
        print(f"RUN {label}")
        rec = _process_one(client, label, path, timeout=timeout)
        results.append(rec)
        routes = rec.get("route_counts") or {}
        print(
            f"  status={rec.get('document_status')} "
            f"pages={rec.get('page_count')} "
            f"routes={routes} "
            f"duration={rec.get('duration_seconds')}s "
            f"pass={rec.get('pass')}"
        )
        overall_pass = overall_pass and bool(rec.get("pass"))

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_pass": overall_pass,
        "subset_only": subset_only,
        "cases": results,
    }
    out = OUT_DIR / "acceptance.local.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"WROTE {out.as_posix()} overall_pass={overall_pass}")
    dumped = json.dumps(payload)
    for banned in BANNED_TOKENS:
        if banned.lower() in dumped.lower():
            print(f"FAIL: banned token leaked into report: {banned}")
            return 1
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
