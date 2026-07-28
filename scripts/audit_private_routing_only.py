#!/usr/bin/env python3
"""Routing-only audit for opaque private documents (no full visual OCR).

Reads a gitignored local manifest mapping opaque labels to relative private paths.
Outputs sanitised page tables and reason distributions only — never text, filenames,
or local absolute paths.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from backend.app.contracts.canonical import CanonicalisationMethod
from backend.app.contracts.native import NativePageDecision, NativePageResult
from backend.app.extraction.native.document_policy import (
    apply_document_escalation,
    decide_document_policy,
)
from backend.app.extraction.native.geometry_quality import GeometryMetrics
from backend.app.extraction.native.image_dominance import ImageDominanceMetrics
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    NativeTrustPolicyConfig,
    PageExtractionCandidate,
)
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.pypdf_inspector import inspect_canonical_pdf
from backend.app.extraction.native.serializer import build_page_result
from backend.app.extraction.native.text_quality import TextStructureMetrics
from backend.app.extraction.native.trust_policy import decide_page_trust
from backend.app.extraction.native.unicode_quality import (
    ExtendedUnicodeMetrics,
    UnicodeMetrics,
    analyse_unicode_extended,
)
from backend.app.extraction.routing.digital_native import (
    is_recoverable_escalation_suppressed,
    is_trusted_digital_native,
    restore_escalation_suppressed_native,
)
from backend.app.extraction.routing.embedded_ocr import (
    is_embedded_ocr_candidate,
    page_is_image_dominant,
)
from backend.app.extraction.routing.full_ocr import needs_full_visual_ocr
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.settings.config import Settings

MANIFEST_NAME = "phase45-routing.local.json"
PRIVATE_ROOT = Path("fixtures/private")
DEFAULT_LABEL = "private_text_rich_097"


def _load_manifest(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a JSON object")
    return data


def _failed_rule(
    reason_codes: list[str], unicode_ratios: dict[str, float], policy: NativeTrustPolicyConfig
) -> tuple[str | None, float | None, float | None]:
    """Return failed_rule, threshold, and actual metric for the dominant hard rule."""

    checks = [
        (
            "high_replacement_character_ratio",
            unicode_ratios.get("replacement_character_ratio", 0.0),
            policy.native_max_replacement_ratio,
        ),
        (
            "high_control_character_ratio",
            unicode_ratios.get("control_character_ratio", 0.0),
            policy.native_max_control_ratio,
        ),
        (
            "high_private_use_character_ratio",
            unicode_ratios.get("private_use_character_ratio", 0.0),
            policy.native_max_private_use_ratio,
        ),
        (
            "high_unassigned_character_ratio",
            unicode_ratios.get("unassigned_character_ratio", 0.0),
            policy.native_max_unassigned_ratio,
        ),
        (
            "high_noncharacter_ratio",
            unicode_ratios.get("noncharacter_ratio", 0.0),
            policy.native_max_unassigned_ratio,
        ),
        (
            "high_unprintable_character_ratio",
            unicode_ratios.get("unprintable_character_ratio", 0.0),
            policy.native_max_control_ratio,
        ),
    ]
    for code, actual, limit in checks:
        if code in reason_codes and actual > limit:
            return code, limit, round(actual, 6)
    for code in reason_codes:
        if code.startswith("high_") or code in {
            "image_dominant_page",
            "excessive_near_overprint_duplicates",
            "excessive_duplicate_characters",
            "native_trust_score_below_threshold",
            "document_visual_authority_escalation",
        }:
            return code, None, None
    return None, None, None


def _proposed_route(page: NativePageResult, policy: RoutingPolicy) -> tuple[str, list[str], bool]:
    restored = False
    if is_recoverable_escalation_suppressed(page):
        restored = True
    page = restore_escalation_suppressed_native(page)
    image_dominant = page_is_image_dominant(page)
    if page.decision is NativePageDecision.ERROR:
        return "page_failed", ["native_extraction_error"], restored
    if is_trusted_digital_native(page, visibility=None, image_dominant=image_dominant):
        reasons = ["trusted_digital_native_text"]
        if restored:
            reasons.append("recovered_after_document_escalation")
        return "digital_native", reasons, restored
    if is_embedded_ocr_candidate(page, policy):
        return "embedded_ocr_verified", ["embedded_ocr_candidate"], restored
    if needs_full_visual_ocr(page) or page.trust.visual_processing_required:
        return "full_visual_ocr", ["full_visual_ocr_required"], restored
    if page.decision is NativePageDecision.ACCEPTED:
        return "digital_native", ["trusted_digital_native_text"], restored
    return "full_visual_ocr", ["legacy_visual_required"], restored


def _validation_status(ratio: float, limit: float) -> str:
    if ratio <= 0.0:
        return "clean"
    if ratio > limit:
        return "failed"
    return "warn"


def _audit_label(label: str, pdf_path: Path) -> dict[str, object]:
    import pdfplumber
    from pypdf import PdfReader

    settings = Settings()
    policy = NativeTrustPolicyConfig(
        native_trust_policy_version=settings.native_trust_policy_version,
    )
    routing = RoutingPolicy.from_settings(settings)
    reader = PdfReader(str(pdf_path))
    with pdfplumber.open(pdf_path) as doc:
        pages_meta: list[CanonicalPageRef] = []
        for i, page in enumerate(doc.pages):
            rotation = 0
            if i < len(reader.pages):
                rotation = int(reader.pages[i].rotation or 0) % 360
            pages_meta.append(
                CanonicalPageRef(
                    page_number=i + 1,
                    width_points=float(page.width),
                    height_points=float(page.height),
                    intrinsic_rotation=rotation,
                    source_type="pdf",
                )
            )
    inspect_canonical_pdf(
        pdf_path,
        pages_meta,
        dimension_tolerance=policy.canonical_page_dimension_tolerance_points,
    )
    candidates = extract_page_candidates(pdf_path, pages_meta, policy)
    page_results: list[NativePageResult] = []
    trusts = []
    candidate_by_page: dict[int, PageExtractionCandidate] = {}
    unicode_by_page: dict[
        int,
        tuple[
            UnicodeMetrics,
            ExtendedUnicodeMetrics,
            GeometryMetrics,
            TextStructureMetrics,
            ImageDominanceMetrics,
        ],
    ] = {}
    for candidate, meta in zip(candidates, pages_meta, strict=True):
        metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(candidate, policy)
        extended = analyse_unicode_extended(candidate.characters)
        unicode_by_page[candidate.page_number] = (unicode_m, extended, geometry_m, text_m, image_m)
        candidate_by_page[candidate.page_number] = candidate
        bundle = decide_page_trust(
            candidate,
            metrics=metrics,
            geometry_m=geometry_m,
            unicode_m=unicode_m,
            text_m=text_m,
            image_m=image_m,
            policy=policy,
            source_type=meta.source_type,
        )
        trusts.append(bundle.trust)
        page_results.append(
            build_page_result(
                bundle,
                canonicalisation_method=CanonicalisationMethod.ORIGINAL_PDF.value,
            )
        )

    phase3_policy = decide_document_policy(trusts, policy=policy, all_pages_image_source=False)
    escalated = apply_document_escalation(page_results, document_policy=phase3_policy)
    document_escalation_applied = phase3_policy.value == "visual"

    table = []
    reason_counts: Counter[str] = Counter()
    route_totals: Counter[str] = Counter()
    unicode_fail_counts: Counter[str] = Counter()
    restored_count = 0
    recognition_eligible = 0
    repair_eligible = 0
    for page_result in escalated:
        page_number = page_result.page_number
        unicode_m, extended, geometry_m, text_m, image_m = unicode_by_page[page_number]
        candidate = candidate_by_page[page_number]
        words = candidate.words or []
        chars = candidate.characters or []
        native_word_count = len(words)
        native_char_count = sum(len(w.text) for w in words) if words else len(chars)
        unicode_ratios = {
            "replacement_character_ratio": unicode_m.replacement_character_ratio,
            "control_character_ratio": unicode_m.control_character_ratio,
            "private_use_character_ratio": unicode_m.private_use_character_ratio,
            "unassigned_character_ratio": unicode_m.unassigned_character_ratio,
            "noncharacter_ratio": unicode_m.noncharacter_ratio,
            "unprintable_character_ratio": unicode_m.unprintable_character_ratio,
            "symbol_character_ratio": extended.symbol_character_ratio,
            "checkbox_like_ratio": extended.checkbox_like_ratio,
            "dingbat_like_ratio": extended.dingbat_like_ratio,
            "format_character_ratio": extended.format_character_ratio,
            "surrogate_character_ratio": extended.surrogate_character_ratio,
            "punctuation_character_ratio": extended.punctuation_character_ratio,
        }
        route, route_reasons, restored = _proposed_route(page_result, routing)
        if restored:
            restored_count += 1
        reason_counts.update(route_reasons)
        reason_counts.update(page_result.trust.reason_codes)
        route_totals[route] += 1
        for code in page_result.trust.reason_codes:
            if "character_ratio" in code or "unicode" in code or "cid" in code or "symbol" in code:
                unicode_fail_counts[code] += 1

        failed_rule, failed_threshold, actual_metric = _failed_rule(
            list(page_result.trust.reason_codes), unicode_ratios, policy
        )
        image_dominant = page_is_image_dominant(page_result)
        embedded = is_embedded_ocr_candidate(page_result, routing)
        visual_agree_eligible = embedded and not image_dominant
        recog_eligible = visual_agree_eligible and native_word_count > 0
        if recog_eligible:
            recognition_eligible += 1
        # Targeted repair: rejected page with verification words + limited unicode pressure.
        if (
            page_result.decision
            in {
                NativePageDecision.REJECTED,
                NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION,
            }
            and (page_result.verification_words or [])
            and unicode_m.private_use_character_ratio <= 0.05
        ):
            repair_eligible += 1

        hard_codes = [
            c for c in page_result.trust.reason_codes if c != "document_visual_authority_escalation"
        ]
        table.append(
            {
                "page_number": page_number,
                "native_candidate_available": native_word_count > 0 or len(chars) > 0,
                "candidate_source": "pdf_text" if native_word_count or chars else "none",
                "native_word_count": native_word_count,
                "native_character_count": native_char_count,
                "native_trust_score": page_result.trust.native_trust_score,
                "unicode_validation_status": _validation_status(
                    max(
                        unicode_m.replacement_character_ratio
                        / max(policy.native_max_replacement_ratio, 1e-9),
                        unicode_m.control_character_ratio
                        / max(policy.native_max_control_ratio, 1e-9),
                        unicode_m.private_use_character_ratio
                        / max(policy.native_max_private_use_ratio, 1e-9),
                        unicode_m.unassigned_character_ratio
                        / max(policy.native_max_unassigned_ratio, 1e-9),
                    )
                    * min(
                        policy.native_max_private_use_ratio,
                        policy.native_max_replacement_ratio,
                    ),
                    policy.native_max_private_use_ratio,
                )
                if True
                else "clean",
                "unicode_ratios": {k: round(v, 6) for k, v in unicode_ratios.items()},
                "unicode_counts": {
                    "replacement": extended.replacement_count,
                    "control": extended.control_count,
                    "private_use": extended.private_use_count,
                    "unassigned": extended.unassigned_count,
                    "surrogate": extended.surrogate_count,
                    "format": extended.format_count,
                    "symbol": extended.symbol_count,
                    "punctuation": extended.punctuation_count,
                    "checkbox_like": extended.checkbox_like_count,
                    "dingbat_like": extended.dingbat_like_count,
                    "non_whitespace_total": extended.non_whitespace_total,
                },
                "geometry_validation_status": (
                    "failed"
                    if geometry_m.invalid_geometry_ratio > policy.native_max_invalid_geometry_ratio
                    else "clean"
                ),
                "duplicate_validation_status": (
                    "failed" if page_result.trust.duplicate_hard_rejection else "clean"
                ),
                "visibility_status": "not_evaluated_routing_only",
                "phase3_page_decision": page_result.decision.value,
                "phase3_hard_rejection": page_result.trust.hard_rejection,
                "phase3_reason_codes": list(page_result.trust.reason_codes),
                "document_escalation_applied": document_escalation_applied
                and "document_visual_authority_escalation" in page_result.trust.reason_codes,
                "page_restored_after_escalation": restored,
                "embedded_ocr_candidate": embedded,
                "visual_agreement_eligible": visual_agree_eligible,
                "recognition_check_eligible": recog_eligible,
                "proposed_route": route,
                "route_reason_codes": route_reasons,
                "failed_rule": failed_rule,
                "failed_threshold": failed_threshold,
                "actual_metric_value": actual_metric,
                "image_count": len(getattr(candidate, "images", []) or []),
                "image_dominant": image_dominant,
                "font_resource_present": any(getattr(c, "fontname", None) for c in chars[:50]),
            }
        )
        # Fix unicode_validation_status properly
        unicode_failed = any(
            code
            in {
                "high_replacement_character_ratio",
                "high_control_character_ratio",
                "high_private_use_character_ratio",
                "high_unassigned_character_ratio",
                "high_noncharacter_ratio",
                "high_unprintable_character_ratio",
            }
            for code in hard_codes
        )
        table[-1]["unicode_validation_status"] = (
            "failed"
            if unicode_failed
            else (
                "warn"
                if any(
                    unicode_ratios[k] > 0
                    for k in (
                        "private_use_character_ratio",
                        "replacement_character_ratio",
                        "control_character_ratio",
                    )
                )
                else "clean"
            )
        )

    totals = {
        "digital_native": int(route_totals.get("digital_native", 0)),
        "embedded_ocr_verified": int(route_totals.get("embedded_ocr_verified", 0)),
        "embedded_ocr_targeted_repair": int(route_totals.get("embedded_ocr_targeted_repair", 0)),
        "full_visual_ocr": int(route_totals.get("full_visual_ocr", 0)),
        "visual_no_text": int(route_totals.get("visual_no_text", 0)),
        "page_failed": int(route_totals.get("page_failed", 0)),
    }

    return {
        "label": label,
        "page_count": len(table),
        "phase3_provisional_policy": phase3_policy.value,
        "document_escalation_applied": document_escalation_applied,
        "pages_restored_after_escalation": restored_count,
        "pages_requiring_recognition_checks": recognition_eligible,
        "pages_eligible_for_targeted_repair": repair_eligible,
        "pages": table,
        "route_totals": totals,
        "reason_distribution": dict(reason_counts),
        "unicode_failure_distribution": dict(unicode_fail_counts),
        "policy_version": policy.native_trust_policy_version,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PRIVATE_ROOT / MANIFEST_NAME,
        help="Gitignored local routing manifest",
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Opaque label to audit (default: {DEFAULT_LABEL})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path under temp/ for sanitised JSON output",
    )
    args = parser.parse_args(argv)
    if not args.manifest.is_file():
        print(json.dumps({"pass": False, "error": "manifest_missing"}))
        return 2

    manifest = _load_manifest(args.manifest)
    relative: str | None = None
    if args.label in manifest and isinstance(manifest[args.label], str):
        relative = str(manifest[args.label])
    else:
        docs = manifest.get("documents")
        if isinstance(docs, dict) and args.label in docs:
            relative = str(docs[args.label])
        elif isinstance(docs, list):
            for entry in docs:
                if isinstance(entry, dict) and entry.get("opaque_label") == args.label:
                    relative = str(entry.get("relative_path") or entry.get("path") or "")
                    break
    if not relative:
        print(json.dumps({"pass": False, "error": "label_missing", "label": args.label}))
        return 2

    pdf_path = (PRIVATE_ROOT / relative).resolve()
    if not pdf_path.is_file() or PRIVATE_ROOT.resolve() not in pdf_path.parents:
        print(json.dumps({"pass": False, "error": "fixture_missing", "label": args.label}))
        return 2

    started = time.perf_counter()
    try:
        result = _audit_label(args.label, pdf_path)
        result["duration_ms"] = int((time.perf_counter() - started) * 1000)
        result["pass"] = True
        payload = json.dumps(result, indent=2, sort_keys=True)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(payload, encoding="utf-8")
        # Compact summary to stdout (full table to --out when provided).
        pages_raw = result.get("pages")
        pages_list = pages_raw if isinstance(pages_raw, list) else []
        summary = {
            "label": result["label"],
            "page_count": result["page_count"],
            "route_totals": result["route_totals"],
            "reason_distribution": result["reason_distribution"],
            "unicode_failure_distribution": result["unicode_failure_distribution"],
            "phase3_provisional_policy": result["phase3_provisional_policy"],
            "document_escalation_applied": result["document_escalation_applied"],
            "pages_restored_after_escalation": result["pages_restored_after_escalation"],
            "pages_requiring_recognition_checks": result["pages_requiring_recognition_checks"],
            "pages_eligible_for_targeted_repair": result["pages_eligible_for_targeted_repair"],
            "policy_version": result["policy_version"],
            "duration_ms": result["duration_ms"],
            "pass": True,
            "failed_rule_distribution": dict(
                Counter(
                    str(p.get("failed_rule"))
                    for p in pages_list
                    if isinstance(p, dict) and p.get("failed_rule")
                )
            ),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        if args.out is None:
            # Still emit page table when no out file (truncated keys).
            print(json.dumps({"pages": result["pages"]}, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "pass": False,
                    "label": args.label,
                    "error": type(exc).__name__,
                    "detail": str(exc)[:200],
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
