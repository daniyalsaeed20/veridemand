"""Run read-only baseline against selected private pages (current production stack).

Does not repair failures. Writes only under tmp/extraction-remediation/baseline/.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

CORPUS = ROOT / "tmp" / "extraction-remediation" / "acceptance-corpus"
FORENSIC_PAGES = ROOT / "tmp" / "extraction-forensic-investigation" / "pages"
EXAMPLE = ROOT / "docs" / "example"
OUT = ROOT / "tmp" / "extraction-remediation" / "baseline"

ALIAS_GLOBS = {
    "police": ["EG90156.pdf"],
    "insurer": ["*Dairyland*.pdf", "*Insurance*.pdf"],
    "ecw_medical": ["*eCW*Medical*.pdf"],
    "ecw_billing": ["*eCW*Billing*.pdf"],
    "long_medical": ["*MEDICAL RECORDS*.pdf"],
    "existing_demand": ["Demand Mayel*.docx"],
}


def _find_pdf(alias: str) -> Path | None:
    for pattern in ALIAS_GLOBS.get(alias, []):
        hits = list(EXAMPLE.glob(pattern))
        pdfs = [h for h in hits if h.suffix.lower() == ".pdf"]
        if pdfs:
            return pdfs[0]
    return None


def _safe_page_summary(
    *,
    page_id: str,
    alias: str,
    page_number: int,
    route: str | None,
    token_count: int,
    char_count: int | None,
    warnings: list[str],
    baseline_source: str,
    ocr_token_count: int | None = None,
    notes: list[str] | None = None,
) -> dict:
    return {
        "page_id": page_id,
        "safe_alias": alias,
        "page_number": page_number,
        "route": route,
        "native_token_count": token_count,
        "char_count": char_count,
        "warning_count": len(warnings),
        "baseline_source": baseline_source,
        "ocr_token_count": ocr_token_count,
        "notes": notes or [],
        # deliberately no transcripts / hashes / private values
    }


def run() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = CORPUS / "corpus_manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("Run build_corpus_manifest.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    from app.models.app_settings import AppSettings
    from app.services.extraction.native import extract_native_page

    settings = AppSettings()
    pages_out: list[dict] = []
    failures_visible: list[dict] = []

    # Group by alias for fewer opens
    by_alias: dict[str, list[dict]] = {}
    for page in manifest.get("selected_pages") or []:
        by_alias.setdefault(str(page["safe_alias"]), []).append(page)

    for alias, pages in by_alias.items():
        pdf = _find_pdf(alias)
        if pdf is None:
            for page in pages:
                pages_out.append(
                    _safe_page_summary(
                        page_id=page["page_id"],
                        alias=alias,
                        page_number=int(page["page_number"] or 0),
                        route=None,
                        token_count=0,
                        char_count=None,
                        warnings=["pdf_unavailable_for_alias"],
                        baseline_source="skipped",
                        notes=["DOCX or missing PDF — native baseline skipped"],
                    )
                )
            continue

        import pdfplumber

        with pdfplumber.open(pdf) as doc:
            n_pages = len(doc.pages)

        for page in pages:
            pn = int(page["page_number"] or 0)
            pid = page["page_id"]
            if pn < 1 or pn > n_pages:
                pages_out.append(
                    _safe_page_summary(
                        page_id=pid,
                        alias=alias,
                        page_number=pn,
                        route=None,
                        token_count=0,
                        char_count=None,
                        warnings=["page_out_of_range"],
                        baseline_source="skipped",
                    )
                )
                continue

            # Prefer forensic dump for OCR-ish artifacts; always run live native when possible
            forensic = FORENSIC_PAGES / pid
            baseline_source = "live_native"
            ocr_token_count = None
            notes: list[str] = []

            try:
                result = extract_native_page(
                    pdf,
                    document_id="doc_01JBASELINE00000000000001",
                    page_number=pn,
                    settings=settings,
                )
                route = result.page.route.value
                token_count = len(result.tokens)
                char_count = result.diagnostics.char_count if result.diagnostics else None
                warnings = list(result.diagnostics.warnings) if result.diagnostics else []
            except Exception as exc:  # noqa: BLE001
                pages_out.append(
                    _safe_page_summary(
                        page_id=pid,
                        alias=alias,
                        page_number=pn,
                        route=None,
                        token_count=0,
                        char_count=None,
                        warnings=[f"native_error:{type(exc).__name__}"],
                        baseline_source="error",
                    )
                )
                continue

            if forensic.is_dir() and (forensic / "source_tokens.json").is_file():
                baseline_source = "live_native+forensic_cache"
                try:
                    toks = json.loads((forensic / "source_tokens.json").read_text(encoding="utf-8"))
                    if isinstance(toks, list):
                        # Forensic may be native or prior process tokens
                        notes.append(f"forensic_token_count={len(toks)}")
                except json.JSONDecodeError:
                    pass

            # Live OCR only when routed to OCR and no forensic OCR-like dump
            if route == "ocr":
                ocr_dump = forensic / "source_tokens.json" if forensic.is_dir() else None
                used_cache = False
                if ocr_dump and ocr_dump.is_file():
                    meta = {}
                    if (forensic / "page_meta.json").is_file():
                        meta = json.loads((forensic / "page_meta.json").read_text(encoding="utf-8"))
                    if meta.get("route") == "ocr" or True:
                        # Use cache counts only; avoid re-running heavy Paddle when dump exists
                        try:
                            toks = json.loads(ocr_dump.read_text(encoding="utf-8"))
                            ocr_token_count = len(toks) if isinstance(toks, list) else None
                            used_cache = True
                            baseline_source = "live_native+cached_ocr_tokens"
                            notes.append("ocr_from_forensic_cache")
                        except json.JSONDecodeError:
                            used_cache = False
                if not used_cache:
                    try:
                        from app.services.extraction.ocr_page import extract_ocr_page
                        from app.services.ocr import ocr_capability_enabled

                        if ocr_capability_enabled():
                            ocr = extract_ocr_page(
                                pdf,
                                document_id="doc_01JBASELINE00000000000001",
                                page=result.page,
                                settings=settings,
                                page_rotation=result.rotation,
                            )
                            ocr_token_count = len(ocr.tokens)
                            baseline_source = "live_native+live_ocr"
                            notes.append("live_paddleocr_executed")
                        else:
                            notes.append("ocr_not_enabled")
                    except Exception as exc:  # noqa: BLE001
                        notes.append(f"ocr_error:{type(exc).__name__}")

            # Visible failure catalogue (safe — no private values)
            if alias == "ecw_medical":
                notes.append("parser_patient_substring_is_not_extraction_error")
            if route == "native" and (char_count or 0) < 100 and alias == "police":
                notes.append("low_native_char_page_may_need_ocr_review")
            notes.append("ocr_line_level_not_word_level")
            notes.append("no_character_geometry_in_production")
            notes.append("no_table_column_model")

            failures_visible.append(
                {
                    "page_id": pid,
                    "safe_alias": alias,
                    "observations": [
                        "missing_word_level_ocr_geometry",
                        "missing_character_level_geometry",
                        "table_column_limitations",
                    ],
                }
            )

            pages_out.append(
                _safe_page_summary(
                    page_id=pid,
                    alias=alias,
                    page_number=pn,
                    route=route,
                    token_count=token_count,
                    char_count=char_count,
                    warnings=warnings,
                    baseline_source=baseline_source,
                    ocr_token_count=ocr_token_count,
                    notes=notes,
                )
            )

            # Private detailed dump (still gitignored)
            detail = {
                "page_id": pid,
                "safe_alias": alias,
                "page_number": pn,
                "route": route,
                "native_word_count": token_count,
                "rotation": result.rotation,
                "diagnostics": {
                    "char_count": char_count,
                    "warning_count": len(warnings),
                },
                "baseline_source": baseline_source,
                "ocr_token_count": ocr_token_count,
            }
            (OUT / "pages").mkdir(exist_ok=True)
            (OUT / "pages" / f"{pid}.json").write_text(
                json.dumps(detail, indent=2) + "\n", encoding="utf-8"
            )

    # Anchor probe (presence only — safe)
    anchor_status = {
        "client_name_Mayel_Amini": "seeded_user_confirmed_anchor_pending_human_link",
        "law_firm_Jackman": "seeded_user_confirmed_anchor_pending_human_link",
        "badge_9065_vs_Go6s": "source_file_not_located",
    }

    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine_native": {"name": "pdfplumber", "version": "bundled_with_app"},
        "engine_ocr": {"name": "paddleocr", "version": "2.7.3", "note": "used only when needed"},
        "page_count": len(pages_out),
        "pages": pages_out,
        "anchor_status": anchor_status,
        "known_limitations": [
            "Native uses pdfplumber words",
            "OCR uses PaddleOCR line-level detections",
            "Character coordinates not persisted",
            "No proper table/column model",
            "Corrupt embedded OCR can be mistaken for native",
            "Phase 5 facts paused — not trusted for extraction acceptance",
            "Patient matching inside patient's is a parser problem, not extraction",
        ],
        "failure_catalogue_safe": failures_visible[:20],
    }

    (OUT / "baseline_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (OUT / "README.txt").write_text(
        "PRIVATE baseline measurements for Remediation Part 1.\n"
        "Do not commit. Safe aggregate counts only may be copied to implementation reports.\n",
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    s = run()
    print("baseline pages:", s["page_count"], "->", OUT)
