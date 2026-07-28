#!/usr/bin/env python3
"""Routing-only audit for opaque private billing documents (no full visual OCR).

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
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import CanonicalPageRef, NativeTrustPolicyConfig
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.pypdf_inspector import inspect_canonical_pdf
from backend.app.extraction.native.serializer import build_page_result
from backend.app.extraction.native.trust_policy import decide_page_trust
from backend.app.extraction.routing.digital_native import (
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
DEFAULT_LABEL = "private_billing_document"


def _load_manifest(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("Manifest must be a JSON object")
    return data


def _proposed_route(page: NativePageResult, policy: RoutingPolicy) -> tuple[str, list[str]]:
    page = restore_escalation_suppressed_native(page)
    image_dominant = page_is_image_dominant(page)
    if page.decision is NativePageDecision.ERROR:
        return "page_failed", ["native_extraction_error"]
    if is_trusted_digital_native(page, visibility=None, image_dominant=image_dominant):
        return "digital_native", ["trusted_digital_native_text"]
    if is_embedded_ocr_candidate(page, policy):
        # Routing-only cannot verify; proposed entry into embedded path.
        return "embedded_ocr_verified", ["embedded_ocr_candidate"]
    words = page.words or page.verification_words or []
    if (
        not words
        and (needs_full_visual_ocr(page) or page.trust.visual_processing_required)
        and page.decision
        in {
            NativePageDecision.ABSENT,
            NativePageDecision.REJECTED,
            NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION,
        }
    ):
        # Blank-like: leave as full OCR unless blank preflight later says no text.
        pass
    if needs_full_visual_ocr(page) or page.trust.visual_processing_required:
        return "full_visual_ocr", ["full_visual_ocr_required"]
    if page.decision is NativePageDecision.ACCEPTED:
        return "digital_native", ["trusted_digital_native_text"]
    return "full_visual_ocr", ["legacy_visual_required"]


def _evidence_consistent(page_result: NativePageResult) -> bool:
    evidence = page_result.trust.metrics.duplicate_layer_evidence
    path = page_result.trust.metrics.hard_rule_path or "none"
    if evidence is None:
        return path == "none" or not page_result.trust.duplicate_hard_rejection
    if evidence.selected_path != path:
        return False
    if evidence.selected_path == "A" and (
        not evidence.path_a_satisfied
        or any(r.mandatory and not r.passed for r in evidence.path_a_rules)
    ):
        return False
    if evidence.selected_path == "B" and (
        not evidence.path_b_satisfied
        or any(r.mandatory and not r.passed for r in evidence.path_b_rules)
    ):
        return False
    if evidence.hard_rejection != (evidence.selected_path in {"A", "B"}):
        return False
    return not (page_result.trust.duplicate_hard_rejection and evidence.selected_path == "none")


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
    page_results = []
    trusts = []
    for candidate, meta in zip(candidates, pages_meta, strict=True):
        metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(candidate, policy)
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

    table = []
    reason_counts: Counter[str] = Counter()
    route_totals: Counter[str] = Counter()
    evidence_ok = True
    for page_result in escalated:
        evidence = page_result.trust.metrics.duplicate_layer_evidence
        route, reasons = _proposed_route(page_result, routing)
        reason_counts.update(reasons)
        reason_counts.update(page_result.trust.reason_codes)
        route_totals[route] += 1
        consistent = _evidence_consistent(page_result)
        evidence_ok = evidence_ok and consistent
        table.append(
            {
                "page_number": page_result.page_number,
                "duplicate_path": (
                    evidence.selected_path if evidence else page_result.trust.metrics.hard_rule_path
                ),
                "duplicate_hard_rejection": page_result.trust.duplicate_hard_rejection,
                "overall_native_hard_rejection": page_result.trust.hard_rejection,
                "phase3_provisional_decision": page_result.decision.value,
                "proposed_phase4_route": route,
                "safe_reason_codes": sorted(set([*reasons, *page_result.trust.reason_codes])),
                "evidence_consistent": consistent,
            }
        )

    # Required totals keys (zero-fill).
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
        "pages": table,
        "route_totals": totals,
        "reason_distribution": dict(reason_counts),
        "evidence_consistent": evidence_ok,
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
        result["pass"] = bool(result.get("evidence_consistent", False))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["pass"] else 1
    except Exception as exc:
        print(
            json.dumps(
                {
                    "pass": False,
                    "label": args.label,
                    "error": type(exc).__name__,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
