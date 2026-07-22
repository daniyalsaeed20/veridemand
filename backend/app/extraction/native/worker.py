"""Native extraction worker entrypoint (subprocess).

Reads a request JSON, extracts/trust-gates native text, and writes a public
result JSON part. Never emits extracted text on stdout/stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.contracts.canonical import CanonicalPageSourceType
from backend.app.contracts.native import (
    DocumentSourcePolicy,
    NativeDocumentSummary,
    NativePageDecision,
    NativePageResult,
    NativeProcessingStatus,
    NativeProgress,
    NativeWarning,
)
from backend.app.contracts.warnings import NativeReasonCode, reason_message
from backend.app.extraction.native.document_policy import (
    apply_document_escalation,
    decide_document_policy,
    user_status_message,
)
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import NativeWorkerRequest
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.pypdf_inspector import inspect_canonical_pdf
from backend.app.extraction.native.serializer import build_page_result
from backend.app.extraction.native.trust_policy import decide_page_trust


def _emit_progress(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _self_check() -> int:
    _emit_progress({"type": "self_check_ok", "pdfplumber": True})
    return 0


def run_worker(request_path: Path, output_path: Path) -> int:
    raw = json.loads(request_path.read_text(encoding="utf-8"))
    request = NativeWorkerRequest.from_dict(raw)
    if request.self_check:
        output_path.write_text(
            json.dumps({"self_check": True, "ok": True}, separators=(",", ":")),
            encoding="utf-8",
        )
        return _self_check()

    policy = request.policy
    if policy.native_extraction_test_delay_seconds > 0:
        time.sleep(policy.native_extraction_test_delay_seconds)

    pdf_path = Path(request.canonical_pdf_path)
    inspect_canonical_pdf(
        pdf_path,
        request.pages,
        dimension_tolerance=policy.canonical_page_dimension_tolerance_points,
    )

    source_by_page = {p.page_number: p.source_type for p in request.pages}
    candidates = extract_page_candidates(pdf_path, request.pages, policy)

    page_results: list[NativePageResult] = []
    for candidate in candidates:
        metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(candidate, policy)
        bundle = decide_page_trust(
            candidate,
            metrics=metrics,
            geometry_m=geometry_m,
            unicode_m=unicode_m,
            text_m=text_m,
            image_m=image_m,
            policy=policy,
            source_type=source_by_page.get(candidate.page_number, "pdf"),
        )
        page_result = build_page_result(
            bundle, canonicalisation_method=request.canonicalisation_method
        )
        page_results.append(page_result)
        _emit_progress(
            {
                "type": "page_completed",
                "page_number": page_result.page_number,
                "decision": page_result.decision.value,
                "source_mode": page_result.source_mode.value,
                "native_trust_score": page_result.trust.native_trust_score,
                "reason_codes": page_result.trust.reason_codes,
            }
        )

    all_image = all(p.source_type == CanonicalPageSourceType.IMAGE.value for p in request.pages)
    trusts = [p.trust for p in page_results]
    document_policy = decide_document_policy(
        trusts, policy=policy, all_pages_image_source=all_image
    )
    page_results = apply_document_escalation(page_results, document_policy=document_policy)

    pages_accepted = sum(1 for p in page_results if p.decision is NativePageDecision.ACCEPTED)
    pages_rejected = sum(1 for p in page_results if p.decision is NativePageDecision.REJECTED)
    pages_absent = sum(1 for p in page_results if p.decision is NativePageDecision.ABSENT)
    pages_errored = sum(1 for p in page_results if p.decision is NativePageDecision.ERROR)
    pages_suppressed = sum(
        1
        for p in page_results
        if p.decision is NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION
    )

    warnings: list[NativeWarning] = []
    if document_policy is DocumentSourcePolicy.VISUAL_AUTHORITY:
        warnings.append(
            NativeWarning(
                code=NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value,
                message=reason_message(NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value),
            )
        )
    if any(p.decision is NativePageDecision.REJECTED for p in page_results):
        warnings.append(
            NativeWarning(
                code=NativeReasonCode.NATIVE_TEXT_REJECTED.value,
                message=reason_message(NativeReasonCode.NATIVE_TEXT_REJECTED.value),
            )
        )

    summary = NativeDocumentSummary(
        document_id=request.document_id,
        native_processing_status=NativeProcessingStatus.COMPLETE,
        document_source_policy=document_policy,
        trust_policy_version=policy.native_trust_policy_version,
        page_count=len(page_results),
        pages_accepted=pages_accepted,
        pages_rejected=pages_rejected,
        pages_absent=pages_absent,
        pages_errored=pages_errored,
        pages_suppressed=pages_suppressed,
        native_result_available=pages_accepted > 0,
        visual_processing_required=pages_accepted < len(page_results) or pages_accepted == 0,
        native_extraction_performed=True,
        final_result_available=False,
        progress=NativeProgress(
            percent=35, pages_completed=len(page_results), pages_total=len(page_results)
        ),
        page_decisions=[p.trust for p in page_results],
        warnings=warnings,
        created_at=datetime.now(UTC),
        user_status_message=user_status_message(document_policy),
    )

    # Validate models before writing.
    page_payloads: list[dict[str, object]] = [p.model_dump(mode="json") for p in page_results]
    for page in page_payloads:
        if page["decision"] != NativePageDecision.ACCEPTED.value:
            page["words"] = []
            page["characters"] = []
            page["provisional_native_text"] = None

    payload: dict[str, object] = {
        "summary": summary.model_dump(mode="json"),
        "pages": page_payloads,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    _emit_progress(
        {
            "type": "document_completed",
            "document_source_policy": document_policy.value,
            "pages_accepted": pages_accepted,
            "pages_total": len(page_results),
        }
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VeriDemand native extraction worker")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        return run_worker(args.request, args.output)
    except Exception as exc:
        # Safe failure: no paths, no text, no stack traces on stdout.
        _emit_progress({"type": "error", "code": "native_worker_failed"})
        sys.stderr.write("native_worker_failed\n")
        sys.stderr.flush()
        del exc
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
