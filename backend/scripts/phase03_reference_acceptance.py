"""Local reference-package OCR acceptance probe (safe aggregates only).

Does not commit outputs. Writes to tmp/phase03_reference_acceptance.json.
Skips gracefully when the Amini/reference package is absent.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.models.app_settings import AppSettings
from app.services.extraction.native import extract_document_native
from app.services.extraction.ocr_page import extract_ocr_page
from app.services.ocr import clear_cancel, ocr_capability_enabled, reset_adapter_state

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "example"
OUT = ROOT / "tmp" / "phase03_reference_acceptance.json"

# Safe aliases only — never log private filenames into committed reports.
ALIASES = {
    "ecw_medical": ["*eCW*Medical*", "*Medical*Records*eCW*", "*ecw*medical*"],
    "ecw_billing": ["*eCW*Billing*", "*Billing*Ledger*", "*ecw*billing*"],
    "police": ["*EG90156*", "*police*"],
    "insurer": ["*Dairyland*", "*Patriot*", "*insurer*"],
    "long_medical": ["*MEDICAL*RECORDS*", "*JACKMAN*", "*medical*stack*"],
}


def _find(alias: str) -> Path | None:
    patterns = ALIASES[alias]
    if not EXAMPLE.is_dir():
        return None
    for pattern in patterns:
        hits = list(EXAMPLE.rglob(pattern))
        pdfs = [h for h in hits if h.suffix.lower() == ".pdf"]
        if pdfs:
            return pdfs[0]
    return None


def _summarize(path: Path, alias: str, settings: AppSettings, *, max_pages: int = 8) -> dict:
    t0 = time.perf_counter()
    native = extract_document_native(path, document_id="doc_01JREF000000000000000001", settings=settings)
    pages = native[:max_pages]
    native_usable = sum(1 for r in pages if r.page.route.value == "native")
    ocr_routed = sum(1 for r in pages if r.page.route.value == "ocr")
    blank = sum(1 for r in pages if r.page.route.value == "manual_review")
    ocr_success = 0
    ocr_warn = 0
    ocr_fail = 0
    token_count = 0
    confs: list[float] = []
    render_ms: list[float] = []
    ocr_ms: list[float] = []
    retries = 0

    for result in pages:
        if result.page.route.value != "ocr":
            continue
        try:
            ocr = extract_ocr_page(
                path,
                document_id="doc_01JREF000000000000000001",
                page=result.page,
                settings=settings,
                page_rotation=result.rotation,
            )
        except Exception as exc:  # noqa: BLE001
            ocr_fail += 1
            continue
        retries += int(ocr.retried)
        render_ms.append(ocr.render_meta.elapsed_render_ms)
        ocr_ms.append(ocr.render_meta.elapsed_ocr_ms)
        token_count += len(ocr.tokens)
        if ocr.assessment.mean_confidence is not None:
            confs.append(ocr.assessment.mean_confidence)
        outcome = ocr.assessment.outcome.value
        if outcome == "ocr_usable":
            ocr_success += 1
        elif outcome in {"ocr_usable_with_warning", "ocr_low_confidence"}:
            ocr_warn += 1
            ocr_success += 1
        else:
            ocr_fail += 1

    return {
        "alias": alias,
        "present": True,
        "pages_sampled": len(pages),
        "native_usable": native_usable,
        "ocr_routed": ocr_routed,
        "blank_or_manual": blank,
        "ocr_success": ocr_success,
        "ocr_warning": ocr_warn,
        "ocr_failure_or_review": ocr_fail,
        "published_token_count": token_count,
        "mean_confidence": (sum(confs) / len(confs)) if confs else None,
        "mean_render_ms": (sum(render_ms) / len(render_ms)) if render_ms else None,
        "mean_ocr_ms": (sum(ocr_ms) / len(ocr_ms)) if ocr_ms else None,
        "preprocess_retry_count": retries,
        "elapsed_total_ms": (time.perf_counter() - t0) * 1000.0,
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    settings = AppSettings()
    report: dict = {
        "ocr_capability_enabled": ocr_capability_enabled(),
        "files": [],
        "notes": [
            "Safe aliases only; private filenames omitted.",
            "Police/insurer may route native under native-first doctrine; OCR path measured on ocr-routed pages.",
        ],
    }
    if not ocr_capability_enabled():
        report["status"] = "skipped_ocr_unavailable"
        OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0

    clear_cancel()
    reset_adapter_state()
    any_present = False
    for alias in ALIASES:
        path = _find(alias)
        if path is None:
            report["files"].append({"alias": alias, "present": False})
            continue
        any_present = True
        max_pages = 24 if alias == "ecw_medical" else (6 if alias == "long_medical" else 4)
        report["files"].append(_summarize(path, alias, settings, max_pages=max_pages))

    report["status"] = "ok" if any_present else "skipped_no_reference_package"
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "ocr_capability_enabled")}, indent=2))
    for row in report["files"]:
        if not row.get("present"):
            print(f"{row['alias']}: missing")
            continue
        print(
            f"{row['alias']}: pages={row['pages_sampled']} native={row['native_usable']} "
            f"ocr_routed={row['ocr_routed']} ocr_ok={row['ocr_success']} warn={row['ocr_warning']} "
            f"fail={row['ocr_failure_or_review']} tokens={row['published_token_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
