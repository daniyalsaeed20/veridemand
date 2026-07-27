"""Full visual OCR routing helpers and blank-page preflight."""

from __future__ import annotations

from backend.app.contracts.native import NativePageDecision, NativePageResult, SourceMode
from backend.app.contracts.routing import (
    EstimatedCostClass,
    FastOcrPassDiagnostics,
    PageRoute,
    PageRouteDecision,
    PageRouteDecisionStatus,
)
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.text_likelihood import TextLikelihoodResult


def needs_full_visual_ocr(page: NativePageResult) -> bool:
    """Conservative full-OCR requirement when no cheaper route applies."""

    if page.decision in {
        NativePageDecision.ABSENT,
        NativePageDecision.ERROR,
    }:
        return True
    if page.source_mode in {SourceMode.VISUAL_AUTHORITY, SourceMode.IMAGE_AUTHORITY}:
        words = page.words or []
        if not words:
            return True
    return bool(page.trust.visual_processing_required and not (page.words or []))


def build_full_ocr_decision(
    page: NativePageResult,
    policy: RoutingPolicy,
    *,
    reason_codes: list[str],
    image_dominant: bool = False,
    embedded_candidate: bool = False,
    visual_score: float | None = None,
    recognition_score: float | None = None,
    sampled_box_count: int = 0,
    recognition_sample_count: int = 0,
) -> PageRouteDecision:
    words = page.words or []
    chars = page.characters or []
    return PageRouteDecision(
        page_number=page.page_number,
        route=PageRoute.FULL_VISUAL_OCR,
        decision_status=PageRouteDecisionStatus.DECIDED,
        decision_version=policy.version,
        reason_codes=reason_codes,
        native_text_present=bool(words or chars or page.trust.native_text_present),
        native_text_accepted=page.decision is NativePageDecision.ACCEPTED,
        native_word_count=len(words) or page.trust.metrics.word_count,
        native_character_count=len(chars) or page.trust.metrics.character_count,
        native_trust_score=page.trust.native_trust_score,
        page_image_dominant=image_dominant,
        embedded_ocr_candidate=embedded_candidate,
        visual_agreement_evaluated=visual_score is not None,
        visual_agreement_score=visual_score,
        sampled_box_count=sampled_box_count,
        recognition_sample_count=recognition_sample_count,
        recognition_agreement_score=recognition_score,
        full_ocr_required=True,
        estimated_cost_class=EstimatedCostClass.HIGH,
    )


def build_visual_no_text_decision(
    page: NativePageResult,
    policy: RoutingPolicy,
    likelihood: TextLikelihoodResult,
) -> PageRouteDecision:
    return PageRouteDecision(
        page_number=page.page_number,
        route=PageRoute.VISUAL_NO_TEXT,
        decision_status=PageRouteDecisionStatus.DECIDED,
        decision_version=policy.version,
        reason_codes=list(likelihood.reason_codes),
        native_text_present=False,
        native_text_accepted=False,
        native_word_count=0,
        native_character_count=0,
        native_trust_score=page.trust.native_trust_score,
        page_image_dominant=True,
        full_ocr_required=False,
        estimated_cost_class=EstimatedCostClass.LOW,
    )


def evaluate_fast_pass_adequacy(
    *,
    detection_count: int,
    average_confidence: float | None,
    coverage: float,
    min_detections: int,
    min_confidence: float,
    min_coverage: float,
) -> tuple[bool, str | None]:
    """Return (adequate, fallback_reason)."""

    if detection_count < min_detections:
        return False, "low_detection_count"
    if average_confidence is not None and average_confidence < min_confidence:
        return False, "low_average_confidence"
    if coverage < min_coverage:
        return False, "low_spatial_coverage"
    return True, None


def build_fast_pass_diagnostics(
    *,
    primary_limit_side: int,
    primary_duration_ms: int,
    primary_detection_count: int,
    primary_average_confidence: float | None,
    fallback_used: bool,
    fallback_reason: str | None,
    fallback_limit_side: int | None,
    fallback_duration_ms: int | None,
) -> FastOcrPassDiagnostics:
    return FastOcrPassDiagnostics(
        primary_limit_side=primary_limit_side,
        primary_duration_ms=primary_duration_ms,
        primary_detection_count=primary_detection_count,
        primary_average_confidence=primary_average_confidence,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        fallback_limit_side=fallback_limit_side,
        fallback_duration_ms=fallback_duration_ms,
    )
