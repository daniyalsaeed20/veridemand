"""Deterministic page-level hybrid extraction router."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from backend.app.contracts.native import NativePageDecision, NativePageResult
from backend.app.contracts.routing import (
    EstimatedCostClass,
    PageRoute,
    PageRouteDecision,
    PageRouteDecisionStatus,
)
from backend.app.contracts.visual import NativeVisibilityResult
from backend.app.extraction.routing.digital_native import (
    build_digital_native_decision,
    is_trusted_digital_native,
    restore_escalation_suppressed_native,
)
from backend.app.extraction.routing.embedded_coverage import evaluate_embedded_coverage
from backend.app.extraction.routing.embedded_ocr import (
    is_embedded_ocr_candidate,
    page_is_image_dominant,
)
from backend.app.extraction.routing.full_ocr import (
    build_full_ocr_decision,
    build_visual_no_text_decision,
    needs_full_visual_ocr,
)
from backend.app.extraction.routing.materialise_embedded import (
    materialise_verified_embedded_words,
    nonblank_requires_usable_embedded_output,
)
from backend.app.extraction.routing.metrics import log_page_route_decision
from backend.app.extraction.routing.models import RouteExecutionPlan, RoutingPolicy
from backend.app.extraction.routing.native_words import native_words_for_routing
from backend.app.extraction.routing.recognition_check import evaluate_recognition_agreement
from backend.app.extraction.routing.targeted_repair import repair_regions
from backend.app.extraction.routing.text_likelihood import evaluate_text_likelihood
from backend.app.extraction.routing.visual_agreement import (
    evaluate_visual_agreement,
    sample_words_for_agreement,
)
from backend.app.settings.config import Settings
from PIL import Image


class PageRouter:
    """Decide the cheapest trustworthy path for one canonical page."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._policy = RoutingPolicy.from_settings(settings)

    @property
    def policy(self) -> RoutingPolicy:
        return self._policy

    def decide(
        self,
        page: NativePageResult,
        *,
        document_id: str,
        visibility: NativeVisibilityResult | None = None,
        page_image: Image.Image | None = None,
        recognise_crop: Callable[[Image.Image], tuple[str, float]] | None = None,
        cancelled: bool = False,
    ) -> RouteExecutionPlan:
        started = time.perf_counter()
        if cancelled:
            decision = PageRouteDecision(
                page_number=page.page_number,
                route=PageRoute.PAGE_CANCELLED,
                decision_status=PageRouteDecisionStatus.CANCELLED,
                decision_version=self._policy.version,
                reason_codes=["cancelled"],
                estimated_cost_class=EstimatedCostClass.NEGLIGIBLE,
            )
            return self._plan_for(decision)

        if not self._policy.hybrid_enabled:
            page = restore_escalation_suppressed_native(page)
            image_dominant = page_is_image_dominant(page)
            if is_trusted_digital_native(
                page, visibility=visibility, image_dominant=image_dominant
            ):
                decision = build_digital_native_decision(page, self._policy)
            elif needs_full_visual_ocr(page) or page.trust.visual_processing_required:
                decision = build_full_ocr_decision(
                    page,
                    self._policy,
                    reason_codes=["hybrid_routing_disabled"],
                    image_dominant=image_dominant,
                )
            elif page.decision is NativePageDecision.ACCEPTED:
                decision = build_digital_native_decision(page, self._policy)
            else:
                decision = build_full_ocr_decision(
                    page,
                    self._policy,
                    reason_codes=["legacy_visual_required"],
                    image_dominant=image_dominant,
                )
            return self._finish(document_id, decision, started)

        page = restore_escalation_suppressed_native(page)
        image_dominant = page_is_image_dominant(page)

        if is_trusted_digital_native(page, visibility=visibility, image_dominant=image_dominant):
            decision = build_digital_native_decision(page, self._policy)
            return self._finish(document_id, decision, started)

        if (
            is_embedded_ocr_candidate(page, self._policy)
            and page_image is not None
            and self._policy.embedded_visual_enabled
        ):
            return self._decide_embedded(
                page,
                document_id=document_id,
                page_image=page_image,
                recognise_crop=recognise_crop,
                image_dominant=image_dominant,
                started=started,
            )

        words = native_words_for_routing(page)
        if (
            not words
            and page_image is not None
            and self._policy.blank_preflight_enabled
            and (needs_full_visual_ocr(page) or page.trust.visual_processing_required)
        ):
            likelihood = evaluate_text_likelihood(page_image, self._policy)
            if likelihood.appears_blank:
                decision = build_visual_no_text_decision(page, self._policy, likelihood)
                return self._finish(document_id, decision, started)

        reasons = ["full_visual_ocr_required"]
        if image_dominant and not words:
            reasons.append("image_dominant_without_text_layer")
        if page.decision is NativePageDecision.ABSENT:
            reasons.append("native_text_absent")
        decision = build_full_ocr_decision(
            page,
            self._policy,
            reason_codes=reasons,
            image_dominant=image_dominant,
        )
        return self._finish(document_id, decision, started)

    def _decide_embedded(
        self,
        page: NativePageResult,
        *,
        document_id: str,
        page_image: Image.Image,
        recognise_crop: Callable[[Image.Image], tuple[str, float]] | None,
        image_dominant: bool,
        started: float,
    ) -> RouteExecutionPlan:
        words = native_words_for_routing(page)

        coverage = evaluate_embedded_coverage(page_image, words, self._policy)
        if not coverage.adequate:
            decision = build_full_ocr_decision(
                page,
                self._policy,
                reason_codes=["embedded_coverage_insufficient", *coverage.reason_codes],
                image_dominant=image_dominant,
                embedded_candidate=True,
            )
            return self._finish(document_id, decision, started)

        visual = evaluate_visual_agreement(
            page_image,
            page,
            self._policy,
            min_region_variance=self._settings.native_visibility_min_region_variance,
            min_edge_density=self._settings.native_visibility_min_edge_density,
        )
        sampled = sample_words_for_agreement(
            words,
            sample_size=self._policy.visual_sample_size,
            page_number=page.page_number,
        )

        if visual.visual_agreement_score < self._policy.min_visual_agreement:
            fail_ratio = len(visual.failed_box_indices) / max(1, visual.sampled_box_count)
            if (
                self._policy.targeted_repair_enabled
                and fail_ratio <= self._policy.max_fail_ratio_for_repair
                and visual.visual_agreement_score >= self._policy.min_visual_agreement * 0.75
            ):
                decision = self._targeted_decision(
                    page,
                    image_dominant=image_dominant,
                    visual_score=visual.visual_agreement_score,
                    sampled=visual.sampled_box_count,
                    visible_ratio=visual.visible_box_ratio,
                    reasons=["limited_visual_disagreement", *visual.reason_codes],
                    failed_count=len(visual.failed_box_indices),
                )
                return self._finish(document_id, decision, started)
            decision = build_full_ocr_decision(
                page,
                self._policy,
                reason_codes=["embedded_visual_agreement_failed", *visual.reason_codes],
                image_dominant=image_dominant,
                embedded_candidate=True,
                visual_score=visual.visual_agreement_score,
                sampled_box_count=visual.sampled_box_count,
            )
            return self._finish(document_id, decision, started)

        recognition_score = None
        recognition_count = 0
        recognition_failed: list[int] = []
        recognition_reasons: list[str] = []
        if self._policy.embedded_recognition_enabled and recognise_crop is not None:
            recognition = evaluate_recognition_agreement(
                page_image,
                page,
                self._policy,
                recognise_crop=recognise_crop,
            )
            recognition_score = recognition.recognition_agreement_score
            recognition_count = recognition.sample_count
            recognition_failed = list(recognition.failed_sample_indices)
            if recognition.recognition_agreement_score < self._policy.min_recognition_agreement:
                fail_ratio = len(recognition.failed_sample_indices) / max(
                    1, recognition.sample_count
                )
                if (
                    self._policy.targeted_repair_enabled
                    and fail_ratio <= self._policy.max_fail_ratio_for_repair
                ):
                    decision = self._targeted_decision(
                        page,
                        image_dominant=image_dominant,
                        visual_score=visual.visual_agreement_score,
                        recognition_score=recognition_score,
                        sampled=visual.sampled_box_count,
                        recognition_samples=recognition_count,
                        visible_ratio=visual.visible_box_ratio,
                        reasons=["limited_recognition_disagreement", *recognition.reason_codes],
                        failed_count=len(recognition_failed),
                    )
                    return self._finish(document_id, decision, started)
                decision = build_full_ocr_decision(
                    page,
                    self._policy,
                    reason_codes=[
                        "embedded_recognition_agreement_failed",
                        *recognition.reason_codes,
                    ],
                    image_dominant=image_dominant,
                    embedded_candidate=True,
                    visual_score=visual.visual_agreement_score,
                    recognition_score=recognition_score,
                    sampled_box_count=visual.sampled_box_count,
                    recognition_sample_count=recognition_count,
                )
                return self._finish(document_id, decision, started)
            recognition_reasons = list(recognition.reason_codes)
        elif self._policy.embedded_recognition_enabled:
            recognition_reasons = ["recognition_check_engine_unavailable"]

        failed_indices = list(visual.failed_box_indices) + list(recognition_failed)
        materialised = materialise_verified_embedded_words(
            words,
            page_number=page.page_number,
            passed_word_ids=None,
            failed_sample_indices=failed_indices,
            sampled_words=sampled,
            agreement_score=visual.visual_agreement_score,
            width_px=page_image.width,
            height_px=page_image.height,
        )
        likelihood = evaluate_text_likelihood(page_image, self._policy)
        if nonblank_requires_usable_embedded_output(
            page_appears_blank=likelihood.appears_blank,
            verified_word_count=materialised.stats.verified_words,
            verified_line_count=materialised.stats.verified_lines,
        ):
            decision = build_full_ocr_decision(
                page,
                self._policy,
                reason_codes=[
                    "embedded_verified_output_empty",
                    "nonblank_requires_usable_embedded_output",
                    *coverage.reason_codes,
                ],
                image_dominant=image_dominant,
                embedded_candidate=True,
                visual_score=visual.visual_agreement_score,
                recognition_score=recognition_score,
                sampled_box_count=visual.sampled_box_count,
                recognition_sample_count=recognition_count,
            )
            return self._finish(document_id, decision, started)

        decision = PageRouteDecision(
            page_number=page.page_number,
            route=PageRoute.EMBEDDED_OCR_VERIFIED,
            decision_status=PageRouteDecisionStatus.DECIDED,
            decision_version=self._policy.version,
            reason_codes=["embedded_ocr_verified", *recognition_reasons, *coverage.reason_codes],
            native_text_present=True,
            native_text_accepted=page.decision is NativePageDecision.ACCEPTED,
            native_word_count=len(words),
            native_character_count=len(page.characters or []),
            native_trust_score=page.trust.native_trust_score,
            page_image_dominant=image_dominant,
            embedded_ocr_candidate=True,
            visual_agreement_evaluated=True,
            visual_agreement_score=visual.visual_agreement_score,
            sampled_box_count=visual.sampled_box_count,
            visible_box_ratio=visual.visible_box_ratio,
            recognition_sample_count=recognition_count,
            recognition_agreement_score=recognition_score,
            full_ocr_required=False,
            estimated_cost_class=EstimatedCostClass.LOW,
        )
        return self._finish(document_id, decision, started)

    def _targeted_decision(
        self,
        page: NativePageResult,
        *,
        image_dominant: bool,
        visual_score: float | None,
        recognition_score: float | None = None,
        sampled: int = 0,
        recognition_samples: int = 0,
        visible_ratio: float | None = None,
        reasons: list[str],
        failed_count: int,
    ) -> PageRouteDecision:
        words = native_words_for_routing(page)
        return PageRouteDecision(
            page_number=page.page_number,
            route=PageRoute.EMBEDDED_OCR_TARGETED_REPAIR,
            decision_status=PageRouteDecisionStatus.DECIDED,
            decision_version=self._policy.version,
            reason_codes=reasons,
            native_text_present=True,
            native_text_accepted=page.decision is NativePageDecision.ACCEPTED,
            native_word_count=len(words),
            native_character_count=len(page.characters or []),
            native_trust_score=page.trust.native_trust_score,
            page_image_dominant=image_dominant,
            embedded_ocr_candidate=True,
            visual_agreement_evaluated=visual_score is not None,
            visual_agreement_score=visual_score,
            sampled_box_count=sampled,
            visible_box_ratio=visible_ratio,
            recognition_sample_count=recognition_samples,
            recognition_agreement_score=recognition_score,
            targeted_region_count=failed_count,
            full_ocr_required=False,
            estimated_cost_class=EstimatedCostClass.MEDIUM,
        )

    def execute_targeted_repair(
        self,
        page: NativePageResult,
        page_image: Image.Image,
        failed_indices: list[int],
        *,
        recognise_region: Callable[[Image.Image], tuple[int, int]],
    ) -> tuple[list[Any], bool]:
        return repair_regions(
            page_image,
            native_words_for_routing(page),
            failed_indices,
            self._policy,
            page_number=page.page_number,
            recognise_region=recognise_region,
        )

    def _finish(
        self, document_id: str, decision: PageRouteDecision, started: float
    ) -> RouteExecutionPlan:
        duration_ms = int((time.perf_counter() - started) * 1000)
        decision = decision.model_copy(update={"actual_duration_ms": duration_ms})
        log_page_route_decision(
            document_id=document_id,
            page_number=decision.page_number,
            route=decision.route.value,
            reason_codes=decision.reason_codes,
            native_word_count=decision.native_word_count,
            visual_agreement_score=decision.visual_agreement_score,
            sample_count=decision.sampled_box_count,
            recognition_agreement_score=decision.recognition_agreement_score,
            full_ocr_required=decision.full_ocr_required,
            route_duration_ms=duration_ms,
        )
        return self._plan_for(decision)

    @staticmethod
    def _plan_for(decision: PageRouteDecision) -> RouteExecutionPlan:
        route = decision.route
        return RouteExecutionPlan(
            decision=decision,
            skip_full_ocr=route
            in {
                PageRoute.DIGITAL_NATIVE,
                PageRoute.EMBEDDED_OCR_VERIFIED,
                PageRoute.VISUAL_NO_TEXT,
                PageRoute.PAGE_CANCELLED,
            },
            retain_native_text=route
            in {
                PageRoute.DIGITAL_NATIVE,
                PageRoute.EMBEDDED_OCR_VERIFIED,
                PageRoute.EMBEDDED_OCR_TARGETED_REPAIR,
            },
            use_embedded_authority=route
            in {
                PageRoute.EMBEDDED_OCR_VERIFIED,
                PageRoute.EMBEDDED_OCR_TARGETED_REPAIR,
            },
            run_targeted_repair=route is PageRoute.EMBEDDED_OCR_TARGETED_REPAIR,
            run_full_ocr=route is PageRoute.FULL_VISUAL_OCR,
            run_blank_preflight=route is PageRoute.VISUAL_NO_TEXT,
        )


def route_page(
    page: NativePageResult,
    *,
    document_id: str,
    settings: Settings,
    visibility: NativeVisibilityResult | None = None,
    page_image: Image.Image | None = None,
    recognise_crop: Callable[[Image.Image], tuple[str, float]] | None = None,
    cancelled: bool = False,
) -> RouteExecutionPlan:
    """Convenience wrapper for one-shot routing."""

    return PageRouter(settings).decide(
        page,
        document_id=document_id,
        visibility=visibility,
        page_image=page_image,
        recognise_crop=recognise_crop,
        cancelled=cancelled,
    )
