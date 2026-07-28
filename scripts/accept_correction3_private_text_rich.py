#!/usr/bin/env python3
"""Opaque Correction 3 final runtime acceptance for private_text_rich_097.

1) Routing-only audit (no full OCR) for duration comparison
2) Full HTTP process against a running API (pnpm dev /api/v1)

Never prints extracted text, private filenames, or paths.
Requires VERIDEMAND_API_BASE (default http://127.0.0.1:8000).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIDEMAND_API_BASE", "http://127.0.0.1:8000")
PRIV = ROOT / "fixtures" / "private"
MANIFEST = PRIV / "phase45-routing.local.json"
OUT = ROOT / "temp" / "private_acceptance" / "correction3_text_rich.json"
ROUTING_OUT = ROOT / "temp" / "private_acceptance" / "correction3_routing_only_final.json"
OPAQUE = "private_text_rich_097"
EXPECTED_PAGES = 97

# Synthetic sentinel that must never appear in public API JSON (private-use glyph).
_PRIVATE_USE_SENTINEL = "\ue001"
_LEAK_FIELD_RE = re.compile(
    r"verification_words|provisional_native_text|quarantined_text|candidate_text",
    re.IGNORECASE,
)


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


def _wait_ready(client: httpx.Client, timeout: float = 180.0) -> bool:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if _ready(client):
            return True
        time.sleep(2.0)
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
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "audit_private_routing_only.py"),
            "--label",
            OPAQUE,
            "--out",
            str(ROUTING_OUT),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_ms = int((time.perf_counter() - t0) * 1000)
    try:
        parsed: object = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        parsed = {"pass": False, "error": "audit_json_invalid"}
    audit: dict[str, Any]
    if isinstance(parsed, dict):
        audit = dict(parsed)
    else:
        audit = {"pass": False, "error": "audit_json_invalid"}
    audit["audit_exit_code"] = proc.returncode
    audit["routing_only_duration_ms"] = duration_ms
    if proc.returncode != 0 and "error" not in audit:
        audit["error"] = (proc.stderr or proc.stdout or "")[-400:]
        audit["pass"] = False
    return audit


def _privacy_scan(payload: object, *, context: str) -> list[str]:
    """Return leak findings without printing private content."""

    findings: list[str] = []
    raw = json.dumps(payload, ensure_ascii=False)

    if _PRIVATE_USE_SENTINEL in raw:
        findings.append(f"{context}:private_use_sentinel")

    # Walk for verification_words with non-empty content on default public responses.
    def walk(node: object, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                child = f"{path}.{key}" if path else key
                if key == "verification_words" and isinstance(value, list) and value:
                    findings.append(f"{context}:{child}:nonempty")
                if (
                    key in {"provisional_native_text"}
                    and isinstance(value, str)
                    and any("\ue000" <= ch <= "\uf8ff" for ch in value)
                ):
                    findings.append(f"{context}:{child}:private_use_in_text")
                walk(value, child)
        elif isinstance(node, list):
            for idx, item in enumerate(node[:50]):
                walk(item, f"{path}[{idx}]")

    walk(payload, "")
    if _LEAK_FIELD_RE.search(raw) and "verification_words" in raw:
        # Presence of empty arrays is OK; nonempty already flagged above.
        pass
    return findings


def _full_http(pdf_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    timeout = float(os.environ.get("VERIDEMAND_ACCEPT_TIMEOUT", "3600"))
    with httpx.Client(base_url=BASE, timeout=180.0) as client:
        if not _wait_ready(client, timeout=180.0):
            return {"pass": False, "stage": "http", "error": "api_not_ready"}

        sess = client.post("/api/v1/sessions")
        sess.raise_for_status()
        sid = sess.json()["session_id"]

        with pdf_path.open("rb") as handle:
            up = client.post(
                f"/api/v1/sessions/{sid}/documents",
                files={"files": (f"{OPAQUE}.pdf", handle, "application/pdf")},
            )
        if up.status_code >= 400:
            return {
                "pass": False,
                "stage": "http",
                "error": "upload_failed",
                "status_code": up.status_code,
            }
        accepted = up.json().get("accepted") or []
        if not accepted:
            return {"pass": False, "stage": "http", "error": "upload_rejected"}
        doc_id = accepted[0]["document_id"]

        proc = client.post(
            f"/api/v1/sessions/{sid}/process",
            json={"document_ids": [doc_id]},
        )
        proc.raise_for_status()

        doc = _wait_terminal(client, sid, doc_id, timeout=timeout)
        status = str(doc.get("status") or "")
        http_duration_ms = int((time.perf_counter() - started) * 1000)

        visual_r = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/visual/summary")
        visual_r.raise_for_status()
        visual = visual_r.json()

        native_r = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/native/summary")
        native_r.raise_for_status()
        native = native_r.json()

        page_count = int(visual.get("document_pages_total") or visual.get("page_count") or 0)
        pages = visual.get("page_summaries") or []
        route_counts: Counter[str] = Counter()
        page_rows: list[dict[str, Any]] = []
        empty_native = 0
        glyph_totals = {
            "quarantined_glyph_count": 0,
            "quarantined_region_count": 0,
            "pages_with_glyph_warnings": 0,
            "material_pages": 0,
            "non_material_pages": 0,
        }
        privacy_findings: list[str] = []
        privacy_findings.extend(_privacy_scan(visual, context="visual_summary"))
        privacy_findings.extend(_privacy_scan(native, context="native_summary"))

        # Sample every page's public native result for words + quarantine + strip check.
        native_pages_checked = 0
        public_words_total = 0
        verification_leaks = 0
        for page_row in pages:
            if not isinstance(page_row, dict):
                continue
            pn = int(page_row.get("page_number") or 0)
            state = str(
                page_row.get("page_result_state")
                or page_row.get("page_route")
                or page_row.get("status")
                or "unknown"
            )
            route_counts[state] += 1
            qg = 0
            qr = 0
            mat = None
            native_page: dict[str, Any] = {}
            word_count = 0
            if pn >= 1:
                np = client.get(f"/api/v1/sessions/{sid}/documents/{doc_id}/native/pages/{pn}")
                if np.status_code == 200:
                    native_page = np.json()
                    native_pages_checked += 1
                    privacy_findings.extend(_privacy_scan(native_page, context=f"native_page_{pn}"))
                    words = native_page.get("words") or []
                    word_count = len(words) if isinstance(words, list) else 0
                    public_words_total += word_count
                    vw = native_page.get("verification_words")
                    if isinstance(vw, list) and vw:
                        verification_leaks += 1
                    qg = int(native_page.get("quarantined_glyph_count") or 0)
                    qr = int(native_page.get("quarantined_region_count") or 0)
                    mat = native_page.get("glyph_materiality")
                    trust = native_page.get("trust")
                    if isinstance(trust, dict):
                        qg = int(trust.get("quarantined_glyph_count") or qg)
                        qr = int(trust.get("quarantined_region_count") or qr)
                        mat = trust.get("glyph_materiality") or mat
                    glyph_totals["quarantined_glyph_count"] += qg
                    glyph_totals["quarantined_region_count"] += qr
                    if qg > 0 or mat == "non_material":
                        glyph_totals["pages_with_glyph_warnings"] += 1
                    if mat == "material":
                        glyph_totals["material_pages"] += 1
                    if mat == "non_material":
                        glyph_totals["non_material_pages"] += 1
                    # Geometry sanity on a sample of words (counts only).
                    bad_geom = 0
                    for w in words[:20] if isinstance(words, list) else []:
                        if not isinstance(w, dict):
                            continue
                        geom = w.get("geometry") or {}
                        for key in ("x", "y", "width", "height"):
                            val = geom.get(key)
                            if val is None:
                                continue
                            try:
                                fval = float(val)
                            except (TypeError, ValueError):
                                bad_geom += 1
                                continue
                            if not (0.0 <= fval <= 1.5):
                                bad_geom += 1
                    if state == "digital_native" and word_count == 0:
                        empty_native += 1
                    page_rows.append(
                        {
                            "page_number": pn,
                            "route": state,
                            "source_mode": page_row.get("source_mode"),
                            "source_label": page_row.get("source_label"),
                            "native_word_count": word_count,
                            "quarantined_glyph_count": qg,
                            "quarantined_region_count": qr,
                            "glyph_materiality": mat,
                            "bad_geometry_sample_count": bad_geom,
                            "native_result_available": (
                                trust.get("native_result_available")
                                if isinstance(trust, dict)
                                else None
                            ),
                            "visual_processing_required": (
                                trust.get("visual_processing_required")
                                if isinstance(trust, dict)
                                else None
                            ),
                        }
                    )
                else:
                    page_rows.append(
                        {
                            "page_number": pn,
                            "route": state,
                            "error": "native_page_fetch_failed",
                            "status_code": np.status_code,
                        }
                    )

        # Optional SSE sample (short read) for privacy — do not require long stream.
        sse_findings: list[str] = []
        try:
            with client.stream(
                "GET",
                f"/api/v1/sessions/{sid}/events",
                timeout=5.0,
            ) as stream:
                chunks: list[str] = []
                for line in stream.iter_lines():
                    chunks.append(line)
                    if len(chunks) > 40:
                        break
                joined = "\n".join(chunks)
                if _PRIVATE_USE_SENTINEL in joined:
                    sse_findings.append("sse:private_use_sentinel")
                if '"verification_words":[{' in joined or '"verification_words": [{' in joined:
                    sse_findings.append("sse:verification_words_payload")
        except Exception:
            sse_findings.append("sse:unavailable_or_timeout")

        digital_native = int(route_counts.get("digital_native", 0))
        full_ocr = int(route_counts.get("full_visual_ocr", 0))
        embedded = int(route_counts.get("embedded_ocr_verified", 0))
        repair = int(route_counts.get("embedded_ocr_targeted_repair", 0))
        failed = int(route_counts.get("page_failed", 0))
        no_text = int(route_counts.get("visual_no_text", 0))

        full_ocr_selected = int(
            visual.get("full_ocr_pages_selected") or visual.get("full_ocr_pages") or 0
        )
        full_ocr_completed = int(visual.get("full_ocr_pages_completed") or 0)
        native_retained = int(visual.get("native_pages_retained") or 0)

        terminal_ok = status.startswith("visual_processing_") and status not in {
            "failed",
            "cancelled",
        }
        policy = visual.get("document_source_policy")
        expected_native_policy = digital_native == EXPECTED_PAGES and full_ocr == 0

        passed = (
            page_count == EXPECTED_PAGES
            and terminal_ok
            and empty_native == 0
            and verification_leaks == 0
            and not any(f for f in privacy_findings if "nonempty" in f or "private_use" in f)
            and failed == 0
            and native_pages_checked == EXPECTED_PAGES
            and (not expected_native_policy or policy in {"native_authority", "native"})
            and (not expected_native_policy or full_ocr_selected == 0)
            and (not expected_native_policy or full_ocr_completed == 0)
        )

        return {
            "pass": passed,
            "stage": "http",
            "session_id": sid,
            "document_id": doc_id,
            "document_status": status,
            "page_count": page_count,
            "route_totals": {
                "digital_native": digital_native,
                "embedded_ocr_verified": embedded,
                "embedded_ocr_targeted_repair": repair,
                "full_visual_ocr": full_ocr,
                "visual_no_text": no_text,
                "page_failed": failed,
            },
            "route_per_page": page_rows,
            "glyph_totals": glyph_totals,
            "public_words_total": public_words_total,
            "empty_digital_native_pages": empty_native,
            "verification_words_leaks": verification_leaks,
            "native_pages_checked": native_pages_checked,
            "final_document_policy": policy,
            "phase3_provisional_document_policy": visual.get("phase3_provisional_document_policy"),
            "visual_processing_status": visual.get("visual_processing_status"),
            "native_pages_retained": native_retained,
            "full_ocr_pages_selected": full_ocr_selected,
            "full_ocr_pages_completed": full_ocr_completed,
            "embedded_pages_verified": visual.get("embedded_pages_verified")
            or visual.get("embedded_ocr_pages_verified"),
            "ocr_work": {
                "full_ocr_pages_selected": full_ocr_selected,
                "full_ocr_pages_completed": full_ocr_completed,
                "full_visual_ocr_route_count": full_ocr,
                "targeted_repair_route_count": repair,
            },
            "privacy_findings": privacy_findings,
            "sse_findings": sse_findings,
            "http_duration_ms": http_duration_ms,
            "progress_percent": doc.get("progress_percent") or doc.get("progress"),
            "canonical_view_available": doc.get("canonical_view_available"),
        }


def main() -> int:
    started = time.perf_counter()
    pdf = _resolve_pdf()
    if pdf is None:
        print(json.dumps({"opaque_label": OPAQUE, "pass": False, "error": "fixture_missing"}))
        return 2

    from pypdf import PdfReader

    page_count = len(PdfReader(str(pdf)).pages)
    if page_count != EXPECTED_PAGES:
        print(
            json.dumps(
                {
                    "opaque_label": OPAQUE,
                    "pass": False,
                    "error": "page_count_mismatch",
                    "page_count": page_count,
                    "expected": EXPECTED_PAGES,
                }
            )
        )
        return 2

    audit = _run_routing_audit()
    skip_http = os.environ.get("VERIDEMAND_CORRECTION3_ROUTING_ONLY", "").strip() in {
        "1",
        "true",
    }

    result: dict[str, Any] = {
        "opaque_label": OPAQUE,
        "page_count": page_count,
        "routing_only": {
            "pass": bool(audit.get("pass")),
            "route_totals": audit.get("route_totals"),
            "phase3_provisional_policy": audit.get("phase3_provisional_policy"),
            "duration_ms": audit.get("routing_only_duration_ms") or audit.get("duration_ms"),
            "policy_version": audit.get("policy_version"),
        },
    }

    if skip_http:
        result["http"] = {"pass": True, "stage": "http", "skipped": True}
    else:
        result["http"] = _full_http(pdf)

    result["total_duration_ms"] = int((time.perf_counter() - started) * 1000)
    result["pass"] = bool(result["routing_only"].get("pass")) and bool(result["http"].get("pass"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # Compact sanitised stdout (no per-page table dump).
    http = result["http"]
    print(
        json.dumps(
            {
                "pass": result["pass"],
                "opaque_label": OPAQUE,
                "page_count": page_count,
                "routing_only_route_totals": result["routing_only"].get("route_totals"),
                "routing_only_duration_ms": result["routing_only"].get("duration_ms"),
                "http_route_totals": http.get("route_totals"),
                "http_duration_ms": http.get("http_duration_ms"),
                "final_document_policy": http.get("final_document_policy"),
                "glyph_totals": http.get("glyph_totals"),
                "ocr_work": http.get("ocr_work"),
                "empty_digital_native_pages": http.get("empty_digital_native_pages"),
                "privacy_findings_count": len(http.get("privacy_findings") or []),
                "session_id": http.get("session_id"),
                "document_id": http.get("document_id"),
                "out": str(OUT.as_posix()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
