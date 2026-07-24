"""Phase 4.4 private subset HTTP acceptance (opaque labels only).

Usage (while `pnpm dev` is running):

  .venv\\Scripts\\python.exe scripts/accept_phase44_private_subset.py

Never prints OCR/native text, private source filenames, or paths beyond opaque labels.
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
OUT_DIR = ROOT / "tmp" / "phase44-acceptance"
SYNTH = ROOT / "fixtures" / "synthetic" / "uploads" / "valid_single_page.pdf"

CASES: list[tuple[str, Path, str]] = [
    ("private_scan_001", PRIV / "private_scan_001.pdf", "scan"),
    ("private_digital_001", PRIV / "private_digital_001.pdf", "digital"),
    ("private_mixed_001", PRIV / "private_mixed_001.pdf", "mixed"),
]


def _ready(client: httpx.Client) -> bool:
    try:
        r = client.get("/health/ready", timeout=5.0)
        if r.status_code != 200:
            return False
        body = r.json()
        return bool(body.get("status") == "ready")
    except Exception:
        return False


def _wait_terminal(client: httpx.Client, sid: str, doc_id: str, timeout: float) -> dict[str, Any]:
    t0 = time.monotonic()
    last: dict[str, Any] = {}
    terminal_prefixes = ("visual_processing_",)
    terminal_exact = {"failed", "cancelled"}
    while time.monotonic() - t0 < timeout:
        listed = client.get(f"/api/v1/sessions/{sid}")
        if listed.status_code == 404:
            time.sleep(1.0)
            continue
        listed.raise_for_status()
        payload = listed.json()
        docs_list = payload.get("documents")
        if not isinstance(docs_list, list):
            docs_list = []
        docs = {d["document_id"]: d for d in docs_list}
        last = docs.get(doc_id) or {}
        status = str(last.get("status") or "")
        if status.startswith(terminal_prefixes) or status in terminal_exact:
            return last
        time.sleep(1.0)
    return last


def _canonical_checks(
    client: httpx.Client, sid: str, doc_id: str, sha_before: str | None
) -> dict[str, Any]:
    meta = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/canonical/metadata")
    full = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/canonical")
    ranged = client.get(
        f"/api/v1/sessions/{sid}/documents/{doc_id}/canonical",
        headers={"Range": "bytes=0-1023"},
    )
    bad = client.get(
        f"/api/v1/sessions/{sid}/documents/{doc_id}/canonical",
        headers={"Range": "bytes=999999999-"},
    )
    sha = meta.json().get("sha256") if meta.status_code == 200 else None
    result = {
        "metadata_status": meta.status_code,
        "full_status": full.status_code,
        "content_type": full.headers.get("content-type"),
        "accept_ranges": full.headers.get("accept-ranges"),
        "content_length": full.headers.get("content-length"),
        "body_starts_pdf": full.content[:5] == b"%PDF-" if full.content else False,
        "length_matches": (
            full.headers.get("content-length") == str(len(full.content))
            if full.status_code == 200
            else False
        ),
        "range_status": ranged.status_code,
        "range_content_length": ranged.headers.get("content-length"),
        "range_content_range": ranged.headers.get("content-range"),
        "invalid_range_status": bad.status_code,
        "sha256": sha,
        "sha_unchanged": (sha_before is None) or (sha == sha_before),
    }
    if ranged.status_code == 206 and full.status_code == 200 and len(full.content) > 1024:
        result["range_body_ok"] = (
            ranged.content == full.content[:1024] and ranged.headers.get("content-length") == "1024"
        )
    else:
        result["range_body_ok"] = False
    return result


def _process_one(
    client: httpx.Client,
    label: str,
    path: Path,
    kind: str,
    *,
    timeout: float,
) -> dict[str, Any]:
    t0 = time.monotonic()
    session = client.post("/api/v1/sessions").json()
    sid = session["session_id"]
    with path.open("rb") as handle:
        upload = client.post(
            f"/api/v1/sessions/{sid}/documents",
            files={"files": (f"{label}.pdf", handle, "application/pdf")},
        )
    upload.raise_for_status()
    doc_id = upload.json()["accepted"][0]["document_id"]
    client.post(
        f"/api/v1/sessions/{sid}/process", json={"document_ids": [doc_id]}
    ).raise_for_status()

    # Snapshot SHA once canonical ready (poll briefly).
    sha_before: str | None = None
    for _ in range(120):
        snap = client.get(f"/api/v1/sessions/{sid}")
        if snap.status_code != 200:
            time.sleep(0.5)
            continue
        docs = {d["document_id"]: d for d in snap.json().get("documents", [])}
        doc = docs.get(doc_id) or {}
        if doc.get("canonical_view_available"):
            meta = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/canonical/metadata")
            if meta.status_code == 200:
                sha_before = meta.json().get("sha256")
            break
        time.sleep(0.5)

    terminal = _wait_terminal(client, sid, doc_id, timeout)
    duration = round(time.monotonic() - t0, 1)

    visual = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/summary")
    native = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/native/summary")
    canon = _canonical_checks(client, sid, doc_id, sha_before)

    visual_body: dict[str, Any] = {}
    if visual.status_code == 200:
        visual_body = visual.json()

    native_body: dict[str, Any] = {}
    if native.status_code == 200:
        native_body = native.json()

    record = {
        "label": label,
        "kind": kind,
        "pass": False,
        "duration_seconds": duration,
        "document_status": terminal.get("status"),
        "page_count": terminal.get("canonical_page_count")
        or visual_body.get("page_count")
        or native_body.get("page_count"),
        "canonical_view_available": bool(terminal.get("canonical_view_available")),
        "native_result_available": bool(terminal.get("native_result_available")),
        "visual_processing_performed": bool(terminal.get("visual_processing_performed")),
        "document_source_policy": terminal.get("document_source_policy")
        or visual_body.get("document_source_policy")
        or native_body.get("document_source_policy"),
        "visual_summary_status": visual.status_code,
        "visual_processing_status": visual_body.get("visual_processing_status"),
        "pages_selected": visual_body.get("pages_selected"),
        "pages_completed": visual_body.get("pages_completed"),
        "pages_failed": visual_body.get("pages_failed"),
        "native_pages_retained": visual_body.get("native_pages_retained"),
        "native_summary_status": native.status_code,
        "worker_generation": terminal.get("worker_generation"),
        "failure_code": terminal.get("failure_code"),
        "canonical": canon,
        "session_id": sid,
        "document_id": doc_id,
    }

    # Kind-specific pass rules (HTTP layer; viewer nonblank checked separately).
    canon_ok = (
        canon["metadata_status"] == 200
        and canon["full_status"] == 200
        and canon["body_starts_pdf"]
        and canon["accept_ranges"] == "bytes"
        and canon["invalid_range_status"] == 416
        and canon["sha_unchanged"]
        and (
            canon["range_status"] == 206 and canon.get("range_body_ok")
            if int(canon.get("content_length") or 0) > 1024
            else canon["full_status"] == 200
        )
    )
    visual_summary_ok = visual.status_code == 200
    status = str(terminal.get("status") or "")

    if kind == "scan":
        record["pass"] = (
            canon_ok
            and visual_summary_ok
            and status.startswith("visual_processing_")
            and int(visual_body.get("pages_selected") or 0) >= 1
        )
    elif kind == "digital":
        vstatus = visual_body.get("visual_processing_status")
        selected = int(visual_body.get("pages_selected") or 0)
        retained = int(visual_body.get("native_pages_retained") or 0)
        record["pass"] = (
            canon_ok
            and visual_summary_ok
            and native.status_code == 200
            and bool(terminal.get("native_result_available"))
            and selected == 0
            and retained >= 1
            and vstatus in {"not_required", "visual_processing_complete"}
            and status.startswith("visual_processing_")
        )
    elif kind == "mixed":
        selected = int(visual_body.get("pages_selected") or 0)
        retained = int(visual_body.get("native_pages_retained") or 0)
        policy = record.get("document_source_policy")
        record["pass"] = (
            canon_ok
            and visual_summary_ok
            and status.startswith("visual_processing_")
            and native.status_code == 200
            and selected >= 1
            and retained >= 1
            and policy in {"mixed_authority", "visual_authority", "native_authority"}
        )
    return record


def _inject_failure(client: httpx.Client) -> dict[str, Any]:
    """Requires OCR_INJECT_VISUAL_FAILURE=true on the running backend."""

    if not SYNTH.is_file():
        return {"label": "synthetic_inject", "pass": False, "error": "synthetic_missing"}
    t0 = time.monotonic()
    session = client.post("/api/v1/sessions").json()
    sid = session["session_id"]
    with SYNTH.open("rb") as handle:
        upload = client.post(
            f"/api/v1/sessions/{sid}/documents",
            files={"files": ("synthetic_inject.pdf", handle, "application/pdf")},
        )
    upload.raise_for_status()
    doc_id = upload.json()["accepted"][0]["document_id"]
    # Upload a second doc without inject expectation for concurrency signal.
    client.post(
        f"/api/v1/sessions/{sid}/process", json={"document_ids": [doc_id]}
    ).raise_for_status()
    terminal = _wait_terminal(client, sid, doc_id, 180.0)
    visual = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/summary")
    native = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/native/summary")
    canon = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/canonical")
    record = {
        "label": "synthetic_inject",
        "kind": "inject",
        "duration_seconds": round(time.monotonic() - t0, 1),
        "document_status": terminal.get("status"),
        "visual_summary_status": visual.status_code,
        "native_summary_status": native.status_code,
        "canonical_status": canon.status_code,
        "canonical_view_available": bool(terminal.get("canonical_view_available")),
        "failure_code": terminal.get("failure_code"),
        "pass": False,
        "session_id": sid,
        "document_id": doc_id,
    }
    record["pass"] = (
        visual.status_code == 200
        and canon.status_code == 200
        and bool(terminal.get("canonical_view_available"))
        and str(terminal.get("status") or "").startswith("visual_processing_")
    )
    return record


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    missing = [label for label, path, _ in CASES if not path.is_file()]
    if missing:
        print(f"FAIL: missing opaque files: {missing}")
        return 2

    client = httpx.Client(base_url=BASE, timeout=60.0)
    if not _ready(client):
        print("FAIL: /health/ready not ready")
        return 2

    results: list[dict[str, Any]] = []
    overall_pass = True
    for label, path, kind in CASES:
        timeout = 900.0 if kind == "scan" else 600.0
        print(f"RUN {label} kind={kind}")
        rec = _process_one(client, label, path, kind, timeout=timeout)
        results.append(rec)
        print(
            f"  status={rec.get('document_status')} "
            f"visual_summary={rec.get('visual_summary_status')} "
            f"selected={rec.get('pages_selected')} "
            f"pass={rec.get('pass')} duration={rec.get('duration_seconds')}"
        )
        overall_pass = overall_pass and bool(rec.get("pass"))

    inject_env = os.environ.get("VERIDEMAND_RUN_INJECT", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    inject_record: dict[str, Any] | None = None
    if inject_env:
        print("RUN synthetic_inject")
        inject_record = _inject_failure(client)
        results.append(inject_record)
        print(
            f"  status={inject_record.get('document_status')} "
            f"visual_summary={inject_record.get('visual_summary_status')} "
            f"pass={inject_record.get('pass')}"
        )
        overall_pass = overall_pass and bool(inject_record.get("pass"))

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overall_pass": overall_pass,
        "cases": results,
    }
    out = OUT_DIR / "acceptance.local.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"WROTE {out.as_posix()} overall_pass={overall_pass}")
    # Integrity: ensure no accidental private paths leaked into JSON values.
    dumped = json.dumps(payload)
    for banned in ("MEDICAL", "AMINI", "wellstar", "srmc", "MR 040926"):
        if banned.lower() in dumped.lower():
            print(f"FAIL: banned token leaked into report: {banned}")
            return 1
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
