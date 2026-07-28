"""Route A — trusted digital native text."""

from __future__ import annotations

from backend.app.contracts.native import (
    NativePageDecision,
    NativePageResult,
    RecognitionStatus,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.routing import (
    EstimatedCostClass,
    PageRoute,
    PageRouteDecision,
    PageRouteDecisionStatus,
)
from backend.app.contracts.visual import NativeVisibilityResult
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.routing.models import RoutingPolicy


def is_recoverable_escalation_suppressed(page: NativePageResult) -> bool:
    """True when Phase 3 provisional escalation suppressed an individually trusted page."""

    if page.decision is not NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION:
        return False
    if page.trust.hard_rejection or page.trust.duplicate_hard_rejection:
        return False
    reasons = {str(c) for c in (page.trust.reason_codes or [])}
    if NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value not in reasons:
        return False
    return bool(page.verification_words)


def restore_escalation_suppressed_native(page: NativePageResult) -> NativePageResult:
    """Materialise verification candidates as accepted native words for Route A."""

    if not is_recoverable_escalation_suppressed(page):
        return page
    if page.words:
        return page
    restored = [
        w.model_copy(
            update={
                "recognition_status": RecognitionStatus.ACCEPTED,
                "source_mode": SourceMode.NATIVE_AUTHORITY,
            }
        )
        for w in (page.verification_words or [])
    ]
    new_trust = page.trust.model_copy(
        update={
            "decision": NativePageDecision.ACCEPTED,
            "source_mode": SourceMode.NATIVE_AUTHORITY,
            "native_result_available": True,
            "visual_processing_required": False,
        }
    )
    return page.model_copy(
        update={
            "decision": NativePageDecision.ACCEPTED,
            "source_mode": SourceMode.NATIVE_AUTHORITY,
            "words": restored,
            "trust": new_trust,
            "verification_words": [],
        }
    )


def is_trusted_digital_native(
    page: NativePageResult,
    *,
    visibility: NativeVisibilityResult | None,
    image_dominant: bool,
) -> bool:
    """True when Phase 3 trust + visibility support digital native authority."""

    recoverable = is_recoverable_escalation_suppressed(page)
    if page.decision is NativePageDecision.ACCEPTED:
        if page.source_mode is not SourceMode.NATIVE_AUTHORITY:
            return False
        if page.trust.visual_processing_required:
            return False
    elif recoverable:
        pass
    else:
        return False
    if image_dominant:
        # Image-dominant pages may still carry an embedded OCR layer — not Route A.
        return False
    if visibility is not None and visibility.downgraded:
        return False
    # Visibility probe not yet run is OK for non-image-dominant accepted natives
    # when Phase 3 already accepted geometry/unicode.
    _ = VisualAgreementStatus  # imported for documentation of Phase boundary
    return True


def build_digital_native_decision(
    page: NativePageResult,
    policy: RoutingPolicy,
    *,
    reason_codes: list[str] | None = None,
) -> PageRouteDecision:
    words = page.words or []
    chars = page.characters or []
    reasons = list(reason_codes or ["trusted_digital_native_text"])
    if (
        any(
            str(c) == NativeReasonCode.DOCUMENT_VISUAL_AUTHORITY_ESCALATION.value
            for c in (page.trust.reason_codes or [])
        )
        and "recovered_after_document_escalation" not in reasons
    ):
        reasons = [*reasons, "recovered_after_document_escalation"]
    warning_codes = {str(c) for c in (page.trust.warning_codes or [])}
    if (
        page.quarantined_glyph_count > 0
        or NativeReasonCode.ISOLATED_GLYPHS_QUARANTINED.value in warning_codes
    ) and NativeReasonCode.ISOLATED_GLYPHS_QUARANTINED.value not in reasons:
        reasons = [*reasons, NativeReasonCode.ISOLATED_GLYPHS_QUARANTINED.value]
    return PageRouteDecision(
        page_number=page.page_number,
        route=PageRoute.DIGITAL_NATIVE,
        decision_status=PageRouteDecisionStatus.DECIDED,
        decision_version=policy.version,
        reason_codes=reasons,
        native_text_present=True,
        native_text_accepted=True,
        native_word_count=len(words),
        native_character_count=len(chars),
        native_trust_score=page.trust.native_trust_score,
        page_image_dominant=False,
        embedded_ocr_candidate=False,
        visual_agreement_evaluated=False,
        full_ocr_required=False,
        estimated_cost_class=EstimatedCostClass.NEGLIGIBLE,
    )
