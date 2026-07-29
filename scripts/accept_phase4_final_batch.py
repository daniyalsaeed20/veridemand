"""Phase 4 final multi-document batch acceptance (opaque labels only).

Uploads every locally available document from a gitignored opaque manifest into
one session, records scheduler/route aggregates, and never prints private text
or source filenames.

Manifest (gitignored): fixtures/private/phase4-final-batch.local.json
Example: fixtures/private/phase4-final-batch.local.json.example

Requires VERIDEMAND_API_BASE (default http://127.0.0.1:8000) whose
/health/live git_commit matches repository HEAD.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from scripts.lib.api_process_guard import assert_api_matches_head

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
PRIV = ROOT / "fixtures" / "private"
MANIFEST = PRIV / "phase4-final-batch.local.json"
OUT = ROOT / "temp" / "private_acceptance" / "phase4_final_batch.json"

# Preferred opaque labels when present in the local manifest.
PREFERRED_LABELS = (
    "private_police_scan",
    "private_billing_document",
    "private_billing_digital",
    "private_medical_embedded_ocr",
    "private_text_rich_097",
    "private_scan_001",
    "private_digital_001",
    "private_mixed_001",
    "private_image_photo",
)


def _ready(client: httpx.Client) -> bool:
    try:
        r = client.get("/health/ready", timeout=5.0)
        return r.status_code == 200 and r.json().get("status") == "ready"
    except Exception:
        return False


def _load_documents() -> list[tuple[str, Path]]:
    if not MANIFEST.is_file():
        # Fall back to phase45 routing manifest when the final batch file is absent.
        alt = PRIV / "phase45-routing.local.json"
        if not alt.is_file():
            return []
        payload = json.loads(alt.read_text(encoding="utf-8"))
    else:
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    mapping = payload.get("documents") if isinstance(payload, dict) else None
    if not isinstance(mapping, dict):
        return []
    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for label in PREFERRED_LABELS:
        rel = mapping.get(label)
        if not isinstance(rel, str) or not rel.strip():
            continue
        path = (PRIV / rel).resolve()
        if not str(path).startswith(str(PRIV.resolve())):
            continue
        if path.is_file() and label not in seen:
            found.append((label, path))
            seen.add(label)
    for label, rel in mapping.items():
        if label in seen or not isinstance(rel, str):
            continue
        path = (PRIV / rel).resolve()
        if not str(path).startswith(str(PRIV.resolve())):
            continue
        if path.is_file():
            found.append((str(label), path))
            seen.add(str(label))
    return found


def _wait_all_terminal(
    client: httpx.Client, sid: str, doc_ids: list[str], timeout: float
) -> dict[str, dict[str, Any]]:
    t0 = time.monotonic()
    last: dict[str, dict[str, Any]] = {}
    while time.monotonic() - t0 < timeout:
        listed = client.get(f"/api/v1/sessions/{sid}")
        if listed.status_code != 200:
            time.sleep(2.0)
            continue
        docs = {d["document_id"]: d for d in listed.json().get("documents") or []}
        last = {did: docs.get(did) or {} for did in doc_ids}
        statuses = [str((last[d] or {}).get("status") or "") for d in doc_ids]
        if all(
            s.startswith("visual_processing_") or s in {"failed", "cancelled"} for s in statuses
        ):
            return last
        time.sleep(2.0)
    return last


def _route_counts(summary: dict[str, Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    hist = summary.get("final_route_histogram")
    if isinstance(hist, dict):
        mapping = (
            ("digital_native", "digital_native_pages"),
            ("embedded_ocr_verified", "embedded_ocr_verified_pages"),
            ("embedded_ocr_targeted_repair", "embedded_ocr_targeted_repair_pages"),
            ("full_visual_ocr", "full_visual_ocr_pages"),
            ("visual_no_text", "visual_no_text_pages"),
            ("page_failed", "page_failed_pages"),
            ("page_cancelled", "page_cancelled_pages"),
        )
        for out_key, hist_key in mapping:
            value = int(hist.get(hist_key) or hist.get(out_key) or 0)
            if value:
                counts[out_key] = value
        return counts
    pages = summary.get("page_summaries")
    if isinstance(pages, list):
        for page in pages:
            if not isinstance(page, dict):
                continue
            route = str(page.get("page_result_state") or page.get("page_route") or "unknown")
            if route == "cancelled":
                counts["page_cancelled"] += 1
            else:
                counts[route] += 1
    # Do not map native_pages_retained → digital_native (overlapping diagnostic).
    return counts


def main() -> int:
    docs = _load_documents()
    if not docs:
        print(
            json.dumps(
                {
                    "pass": False,
                    "error": "missing_batch_manifest_or_files",
                    "hint": "Create fixtures/private/phase4-final-batch.local.json",
                }
            )
        )
        return 2

    try:
        identity = assert_api_matches_head(BASE, root=ROOT)
    except RuntimeError as exc:
        print(json.dumps({"pass": False, "error": "build_identity_mismatch", "message": str(exc)}))
        return 2

    batch_start = time.perf_counter()
    time_to_first: float | None = None
    per_doc: list[dict[str, Any]] = []
    route_totals: Counter[str] = Counter()
    total_pages = 0
    success = 0
    failed = 0

    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        if not _ready(client):
            print(json.dumps({"pass": False, "error": "api_not_ready"}))
            return 2

        sess = client.post("/api/v1/sessions").json()
        sid = sess["session_id"]
        uploaded: list[tuple[str, str]] = []
        for label, path in docs:
            with path.open("rb") as handle:
                up = client.post(
                    f"/api/v1/sessions/{sid}/documents",
                    files={"files": (f"{label}.pdf", handle, "application/pdf")},
                )
            up.raise_for_status()
            accepted = up.json().get("accepted") or []
            if not accepted:
                failed += 1
                per_doc.append({"opaque_label": label, "pass": False, "error": "upload_rejected"})
                continue
            uploaded.append((label, accepted[0]["document_id"]))

        if not uploaded:
            print(json.dumps({"pass": False, "error": "no_documents_uploaded"}))
            return 1

        doc_ids = [d for _, d in uploaded]
        client.post(
            f"/api/v1/sessions/{sid}/process",
            json={"document_ids": doc_ids},
        ).raise_for_status()

        # First result: any document leaving queued/native-only into a later status.
        poll_t0 = time.monotonic()
        while time.monotonic() - poll_t0 < 120.0 and time_to_first is None:
            listed = client.get(f"/api/v1/sessions/{sid}")
            if listed.status_code == 200:
                for row in listed.json().get("documents") or []:
                    st = str(row.get("status") or "")
                    if st and st not in {"queued", "pending", "uploading"}:
                        time_to_first = time.perf_counter() - batch_start
                        break
            time.sleep(0.5)

        scheduler: dict[str, Any] = {}
        try:
            sched_resp = client.get(f"/api/v1/sessions/{sid}/scheduler")
            if sched_resp.status_code == 200:
                scheduler = sched_resp.json()
        except Exception:
            scheduler = {}

        finals = _wait_all_terminal(client, sid, doc_ids, timeout=7200.0)

        for label, doc_id in uploaded:
            doc = finals.get(doc_id) or {}
            status = str(doc.get("status") or "")
            visual = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/summary")
            summary: dict[str, Any] = {}
            if visual.status_code == 200:
                summary = visual.json()
            routes = _route_counts(summary)
            route_totals.update(routes)
            pages = int(summary.get("document_pages_total") or summary.get("page_count") or 0)
            total_pages += pages
            ok = status.startswith("visual_processing_")
            if ok:
                success += 1
            else:
                failed += 1
            per_doc.append(
                {
                    "opaque_label": label,
                    "pass": ok,
                    "status": status,
                    "page_count": pages,
                    "route_counts": dict(routes),
                    "full_ocr_pages": int(routes.get("full_visual_ocr", 0)),
                    "targeted_repair_pages": int(routes.get("embedded_ocr_targeted_repair", 0)),
                    "native_or_embedded_pages": int(
                        routes.get("digital_native", 0) + routes.get("embedded_ocr_verified", 0)
                    ),
                }
            )

        # Session reset cleanup check.
        client.delete(f"/api/v1/sessions/{sid}")
        residual_ok = client.get(f"/api/v1/sessions/{sid}").status_code == 404

    total_duration = round(time.perf_counter() - batch_start, 2)
    report = {
        "pass": failed == 0 and success == len(uploaded) and residual_ok,
        "identity": identity,
        "document_count": len(uploaded),
        "total_page_count": total_pages,
        "route_counts": dict(route_totals),
        "selected_full_ocr_page_count": int(route_totals.get("full_visual_ocr", 0)),
        "targeted_repair_page_count": int(route_totals.get("embedded_ocr_targeted_repair", 0)),
        "native_embedded_page_count": int(
            route_totals.get("digital_native", 0) + route_totals.get("embedded_ocr_verified", 0)
        ),
        "batch_start_unix": None,
        "time_to_first_result_s": None if time_to_first is None else round(time_to_first, 2),
        "total_batch_duration_s": total_duration,
        "documents": per_doc,
        "scheduler_snapshot": {
            "policy_version": scheduler.get("policy_version"),
            "queue_depth": scheduler.get("queue_depth"),
            "aging_activations": scheduler.get("aging_activations"),
            "worker_generation": scheduler.get("worker_generation"),
            "model_load_count": scheduler.get("model_load_count"),
            "worker_restart_count": scheduler.get("worker_restart_count"),
        },
        "success_count": success,
        "failure_count": failed,
        "session_reset_cleared": residual_ok,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "pass": report["pass"],
                "document_count": report["document_count"],
                "total_page_count": total_pages,
                "out": str(OUT),
            },
            sort_keys=True,
        )
    )
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
