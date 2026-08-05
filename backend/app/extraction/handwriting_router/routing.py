"""Deterministic Phase 5 route-first vision-reservation routing decisions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from backend.app.contracts.ocr import (
    HandwritingClassificationLifecycle,
    HandwritingClassificationOutcome,
    HandwritingDecisionReason,
    HandwritingInferenceSource,
)
from backend.app.extraction.handwriting_router.constants import EXPECTED_ROUTE_OUTPUTS


@dataclass(frozen=True, slots=True)
class RoutingThresholds:
    local_ocr_safe_threshold: float
    vision_required_threshold: float
    handwriting_accept_threshold: float

    def is_ordered(self) -> bool:
        return self.local_ocr_safe_threshold < self.vision_required_threshold


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    lifecycle: HandwritingClassificationLifecycle
    outcome: HandwritingClassificationOutcome
    decision_reason: HandwritingDecisionReason
    inference_source: HandwritingInferenceSource
    top_class: str | None
    top_score: float | None
    second_score: float | None
    class_margin: float | None
    class_scores: dict[str, float]


def _finite_route(scores: np.ndarray) -> bool:
    return bool(scores.shape == (2,) and np.all(np.isfinite(scores)))


def decide_routing_outcome(
    scores: np.ndarray | list[float] | tuple[float, ...],
    thresholds: RoutingThresholds,
    *,
    labels: tuple[str, str] = EXPECTED_ROUTE_OUTPUTS,
) -> RoutingDecision:
    """Map independent route probabilities to a public routing outcome.

    Precedence (route-first):
      invalid → uncertain
      elif p_route <= local_ocr_safe → printed
      elif p_route >= vision_required and p_hw >= handwriting_accept → handwritten
      else → uncertain

    The model never emits non_text. Printed is granted only below the safe threshold.
    The handwriting_present head never authorises local OCR by itself.
    """

    arr = np.asarray(scores, dtype=np.float64).reshape(-1)
    empty_scores = {label: float("nan") for label in labels}
    if arr.shape != (2,) or not _finite_route(arr):
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.FAILED,
            outcome=HandwritingClassificationOutcome.UNCERTAIN,
            decision_reason=HandwritingDecisionReason.INVALID_OUTPUT,
            inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
            top_class=None,
            top_score=None,
            second_score=None,
            class_margin=None,
            class_scores=empty_scores,
        )
    # Route probabilities must be in [0, 1] (post-sigmoid).
    if np.any(arr < -1e-9) or np.any(arr > 1.0 + 1e-9):
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.FAILED,
            outcome=HandwritingClassificationOutcome.UNCERTAIN,
            decision_reason=HandwritingDecisionReason.INVALID_OUTPUT,
            inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
            top_class=None,
            top_score=None,
            second_score=None,
            class_margin=None,
            class_scores={labels[i]: float(arr[i]) for i in range(2)},
        )

    p_route = float(arr[0])
    p_hw = float(arr[1])
    score_map = {labels[0]: p_route, labels[1]: p_hw}
    local_safe = thresholds.local_ocr_safe_threshold
    vision_req = thresholds.vision_required_threshold
    hw_accept = thresholds.handwriting_accept_threshold

    def _uncertain(
        reason: HandwritingDecisionReason,
        *,
        lifecycle: HandwritingClassificationLifecycle = (
            HandwritingClassificationLifecycle.CLASSIFIED
        ),
        source: HandwritingInferenceSource = HandwritingInferenceSource.SAFETY_ABSTENTION,
    ) -> RoutingDecision:
        return RoutingDecision(
            lifecycle=lifecycle,
            outcome=HandwritingClassificationOutcome.UNCERTAIN,
            decision_reason=reason,
            inference_source=source,
            top_class=labels[0] if p_route >= p_hw else labels[1],
            top_score=max(p_route, p_hw),
            second_score=min(p_route, p_hw),
            class_margin=abs(p_route - p_hw),
            class_scores=score_map,
        )

    # Clear printed: route risk safely low (positively guarded).
    if p_route <= local_safe:
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.CLASSIFIED,
            outcome=HandwritingClassificationOutcome.PRINTED,
            decision_reason=HandwritingDecisionReason.PRINTED_THRESHOLD_MET,
            inference_source=HandwritingInferenceSource.MODEL_INFERENCE,
            top_class="printed",
            top_score=1.0 - p_route,
            second_score=p_route,
            class_margin=abs(p_route - p_hw),
            class_scores=score_map,
        )

    # Clear handwritten: vision required and handwriting evidence accepted.
    if p_route >= vision_req and p_hw >= hw_accept:
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.CLASSIFIED,
            outcome=HandwritingClassificationOutcome.HANDWRITTEN,
            decision_reason=HandwritingDecisionReason.HANDWRITING_THRESHOLD_MET,
            inference_source=HandwritingInferenceSource.MODEL_INFERENCE,
            top_class=labels[1],
            top_score=p_hw,
            second_score=p_route,
            class_margin=abs(p_route - p_hw),
            class_scores=score_map,
        )

    # Grey zone / route-positive but HW-low / anything else → uncertain (never printed).
    if p_route >= vision_req:
        return _uncertain(HandwritingDecisionReason.LOW_TOP_PROBABILITY)
    return _uncertain(HandwritingDecisionReason.LOW_TOP_PROBABILITY)
