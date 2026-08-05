"""Conservative page-level vision reservation (Phase 5 Task C3).

Reuses the existing Phase 4 ``page_is_image_dominant`` predicate. When the
feature flag is enabled, image-dominant pages skip local Paddle recognition and
enter ``vision_reserved_pending_phase_6`` pending Phase 6 (no provider call).
"""

from __future__ import annotations

from backend.app.contracts.native import NativePageResult, SourceMode
from backend.app.contracts.ocr import HandwritingAssessment
from backend.app.contracts.page_vision_reservation import (
    reserved_pending_phase_6_evidence,
)
from backend.app.contracts.routing import PageRoute
from backend.app.contracts.visual import (
    AgreementEvaluationStatus,
    PageResultState,
    VisualPageResult,
    VisualPageStatus,
    VisualWarning,
    source_label_for_page_result_state,
)
from backend.app.extraction.routing.embedded_ocr import page_is_image_dominant
from backend.app.settings.config import Settings

_RESERVATION_REASON_CODE = "page_vision_reservation_image_dominant"
_AUTHORITY_DEFERRED_CODE = "final_authority_deferred_pending_phase_6"
_AUTHORITY_DEFERRED_MESSAGE = (
    "Final extraction authority is deferred because this image-dominant page "
    "requires Phase 6 full-page vision processing. Provisional native or embedded "
    "evidence is retained but is not final authority. Reservation does not claim "
    "the page is proven handwritten."
)


def page_vision_fallback_active(settings: Settings) -> bool:
    """Return True when conservative page-vision fallback may reserve pages."""

    if not settings.handwriting_page_vision_fallback_enabled:
        return False
    mode = str(settings.handwriting_page_vision_fallback_mode or "").strip().lower()
    if mode != "conservative":
        raise ValueError(
            f"HANDWRITING_PAGE_VISION_FALLBACK_MODE must be 'conservative'; got {mode!r}."
        )
    return True


def should_reserve_page_for_vision(
    page: NativePageResult,
    settings: Settings,
) -> bool:
    """Decide reservation using the exact Phase 4 image-dominance predicate."""

    if not page_vision_fallback_active(settings):
        return False
    return page_is_image_dominant(page)


def reserved_page_source_mode(page: NativePageResult) -> SourceMode:
    """Choose a non-final authority mode for a reserved page."""

    if page.source_mode is SourceMode.IMAGE_AUTHORITY:
        return SourceMode.IMAGE_AUTHORITY
    return SourceMode.VISUAL_AUTHORITY


def build_reserved_page_result(
    page: NativePageResult,
    *,
    page_render_available: bool,
) -> VisualPageResult:
    """Materialise an exclusive vision-reserved terminal page result."""

    state = PageResultState.VISION_RESERVED_PENDING_PHASE_6
    return VisualPageResult(
        page_number=page.page_number,
        status=VisualPageStatus.RESERVED_PENDING_PHASE_6,
        source_mode=reserved_page_source_mode(page),
        page_result_state=state,
        source_label=source_label_for_page_result_state(state),
        page_route=PageRoute.VISION_RESERVED_PENDING_PHASE_6.value,
        route_reason_codes=[_RESERVATION_REASON_CODE, _AUTHORITY_DEFERRED_CODE],
        visual_agreement_status=AgreementEvaluationStatus.NOT_REQUIRED,
        recognition_agreement_status=AgreementEvaluationStatus.NOT_REQUIRED,
        visual_result_available=False,
        visual_processing_attempted=False,
        handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
        page_vision_reservation=reserved_pending_phase_6_evidence(
            page_render_available=page_render_available,
        ),
        phase3_page_decision=page.decision.value,
        document_escalation_applied="document_visual_authority_escalation"
        in (page.trust.reason_codes or []),
        warnings=[
            VisualWarning(code=_AUTHORITY_DEFERRED_CODE, message=_AUTHORITY_DEFERRED_MESSAGE)
        ],
    )
