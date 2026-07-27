"""Route A — trusted digital native text."""

from __future__ import annotations

from backend.app.contracts.native import (
    NativePageDecision,
    NativePageResult,
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
from backend.app.extraction.routing.models import RoutingPolicy


def is_trusted_digital_native(
    page: NativePageResult,
    *,
    visibility: NativeVisibilityResult | None,
    image_dominant: bool,
) -> bool:
    """True when Phase 3 trust + visibility support digital native authority."""

    if page.decision is not NativePageDecision.ACCEPTED:
        return False
    if page.source_mode is not SourceMode.NATIVE_AUTHORITY:
        return False
    if page.trust.visual_processing_required:
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
    return PageRouteDecision(
        page_number=page.page_number,
        route=PageRoute.DIGITAL_NATIVE,
        decision_status=PageRouteDecisionStatus.DECIDED,
        decision_version=policy.version,
        reason_codes=reason_codes or ["trusted_digital_native_text"],
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
