"""Document-level source policy and whole-document escalation."""

from __future__ import annotations

from backend.app.contracts.native import (
    DocumentSourcePolicy,
    NativePageDecision,
    NativePageResult,
    NativePageTrustResult,
    SourceMode,
)
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.models import NativeTrustPolicyConfig
from backend.app.extraction.native.serializer import as_verification_words


def _is_failed(trust: NativePageTrustResult) -> bool:
    return (
        trust.decision
        in {
            NativePageDecision.REJECTED,
            NativePageDecision.ABSENT,
            NativePageDecision.ERROR,
        }
        or trust.source_mode is SourceMode.IMAGE_AUTHORITY
    )


def decide_document_policy(
    page_trusts: list[NativePageTrustResult],
    *,
    policy: NativeTrustPolicyConfig,
    all_pages_image_source: bool,
) -> DocumentSourcePolicy:
    if all_pages_image_source:
        return DocumentSourcePolicy.IMAGE_AUTHORITY

    if not page_trusts:
        return DocumentSourcePolicy.VISUAL_AUTHORITY

    if all(t.decision is NativePageDecision.ACCEPTED for t in page_trusts):
        return DocumentSourcePolicy.NATIVE_AUTHORITY

    if all(_is_failed(t) for t in page_trusts):
        return DocumentSourcePolicy.VISUAL_AUTHORITY

    failed = sum(1 for t in page_trusts if _is_failed(t))
    page_count = len(page_trusts)
    if page_count >= 3:
        ratio = failed / page_count
        if (
            failed >= policy.native_document_min_failed_pages
            and ratio >= policy.document_visual_authority_failure_ratio
        ):
            return DocumentSourcePolicy.VISUAL_AUTHORITY

    return DocumentSourcePolicy.MIXED_AUTHORITY


def apply_document_escalation(
    page_results: list[NativePageResult],
    *,
    document_policy: DocumentSourcePolicy,
) -> list[NativePageResult]:
    """Suppress accepted text when the whole document escalates to visual authority."""

    if document_policy is not DocumentSourcePolicy.VISUAL_AUTHORITY:
        return page_results

    updated: list[NativePageResult] = []
    for page in page_results:
        trust = page.trust
        if trust.decision is NativePageDecision.ACCEPTED:
            reasons = list(trust.reason_codes)
            if NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value not in reasons:
                reasons.append(NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value)
            new_trust = trust.model_copy(
                update={
                    "decision": NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION,
                    "source_mode": SourceMode.VISUAL_AUTHORITY,
                    "reason_codes": reasons,
                    "native_result_available": False,
                    "visual_processing_required": True,
                }
            )
            # Move accepted words into verification_words for Phase 4.5.
            retained = as_verification_words(list(page.words or []))
            if not retained and page.verification_words:
                retained = list(page.verification_words)
            updated.append(
                page.model_copy(
                    update={
                        "decision": NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION,
                        "source_mode": SourceMode.VISUAL_AUTHORITY,
                        "trust": new_trust,
                        "words": [],
                        "characters": [],
                        "provisional_native_text": None,
                        "verification_words": retained,
                    }
                )
            )
        else:
            reasons = list(trust.reason_codes)
            if NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value not in reasons:
                reasons.append(NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value)
            new_trust = trust.model_copy(
                update={
                    "source_mode": SourceMode.VISUAL_AUTHORITY
                    if trust.source_mode is not SourceMode.IMAGE_AUTHORITY
                    else trust.source_mode,
                    "reason_codes": reasons,
                    "native_result_available": False,
                    "visual_processing_required": True,
                }
            )
            # Keep existing verification candidates; clear accepted fields only.
            updated.append(
                page.model_copy(
                    update={
                        "trust": new_trust,
                        "words": [],
                        "characters": [],
                        "provisional_native_text": None,
                    }
                )
            )
    return updated


def user_status_message(policy: DocumentSourcePolicy | None) -> str:
    if policy is DocumentSourcePolicy.NATIVE_AUTHORITY:
        return "Native text accepted. Later structure stages have not started."
    if policy is DocumentSourcePolicy.MIXED_AUTHORITY:
        return "Some pages use native text; other pages require visual processing."
    if policy is DocumentSourcePolicy.VISUAL_AUTHORITY:
        return "The native text layer was rejected. Visual processing is required."
    if policy is DocumentSourcePolicy.IMAGE_AUTHORITY:
        return "This document requires visual processing."
    return "Native processing is not complete."
