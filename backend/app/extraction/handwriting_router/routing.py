"""Deterministic Phase 5 safety-first dual-risk routing decisions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from backend.app.contracts.ocr import (
    HandwritingClassificationLifecycle,
    HandwritingClassificationOutcome,
    HandwritingDecisionReason,
    HandwritingInferenceSource,
)
from backend.app.extraction.handwriting_router.constants import EXPECTED_RISK_OUTPUTS


@dataclass(frozen=True, slots=True)
class RoutingThresholds:
    handwriting_accept_threshold: float
    handwriting_safe_low_threshold: float
    non_text_accept_threshold: float
    non_text_safe_low_threshold: float

    def is_ordered(self) -> bool:
        return (
            self.handwriting_safe_low_threshold < self.handwriting_accept_threshold
            and self.non_text_safe_low_threshold < self.non_text_accept_threshold
        )


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


def _finite_risks(scores: np.ndarray) -> bool:
    return bool(scores.shape == (2,) and np.all(np.isfinite(scores)))


def decide_routing_outcome(
    scores: np.ndarray | list[float] | tuple[float, ...],
    thresholds: RoutingThresholds,
    *,
    labels: tuple[str, str] = EXPECTED_RISK_OUTPUTS,
) -> RoutingDecision:
    """Map independent risk probabilities to a public routing outcome.

    Precedence (safety-first):
      invalid → uncertain
      elif p_hw >= hw_accept and p_nt < nt_accept → handwritten
      elif p_hw <= hw_safe_low and p_nt >= nt_accept → non_text
      elif p_hw <= hw_safe_low and p_nt <= nt_safe_low → printed
      else → uncertain

    Printed is granted only when both risks are safely low.
    Material handwriting risk never becomes non_text.
    """

    arr = np.asarray(scores, dtype=np.float64).reshape(-1)
    empty_scores = {label: float("nan") for label in labels}
    if arr.shape != (2,) or not _finite_risks(arr):
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
    # Risk probabilities must be in [0, 1] (post-sigmoid).
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

    p_hw = float(arr[0])
    p_nt = float(arr[1])
    score_map = {labels[0]: p_hw, labels[1]: p_nt}
    hw_accept = thresholds.handwriting_accept_threshold
    hw_safe = thresholds.handwriting_safe_low_threshold
    nt_accept = thresholds.non_text_accept_threshold
    nt_safe = thresholds.non_text_safe_low_threshold

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
            top_class=labels[0] if p_hw >= p_nt else labels[1],
            top_score=max(p_hw, p_nt),
            second_score=min(p_hw, p_nt),
            class_margin=abs(p_hw - p_nt),
            class_scores=score_map,
        )

    # Clear handwritten: high HW risk, non-text not accepted.
    if p_hw >= hw_accept and p_nt < nt_accept:
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.CLASSIFIED,
            outcome=HandwritingClassificationOutcome.HANDWRITTEN,
            decision_reason=HandwritingDecisionReason.HANDWRITING_THRESHOLD_MET,
            inference_source=HandwritingInferenceSource.MODEL_INFERENCE,
            top_class=labels[0],
            top_score=p_hw,
            second_score=p_nt,
            class_margin=abs(p_hw - p_nt),
            class_scores=score_map,
        )

    # Clear non-text: HW safely low AND non-text accepted (never override HW risk).
    if p_hw <= hw_safe and p_nt >= nt_accept:
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.CLASSIFIED,
            outcome=HandwritingClassificationOutcome.NON_TEXT,
            decision_reason=HandwritingDecisionReason.NON_TEXT_THRESHOLD_MET,
            inference_source=HandwritingInferenceSource.MODEL_INFERENCE,
            top_class=labels[1],
            top_score=p_nt,
            second_score=p_hw,
            class_margin=abs(p_hw - p_nt),
            class_scores=score_map,
        )

    # Clear printed: both risks safely low (positively guarded).
    if p_hw <= hw_safe and p_nt <= nt_safe:
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.CLASSIFIED,
            outcome=HandwritingClassificationOutcome.PRINTED,
            decision_reason=HandwritingDecisionReason.PRINTED_THRESHOLD_MET,
            inference_source=HandwritingInferenceSource.MODEL_INFERENCE,
            top_class="printed",
            top_score=1.0 - max(p_hw, p_nt),
            second_score=max(p_hw, p_nt),
            class_margin=abs(p_hw - p_nt),
            class_scores=score_map,
        )

    # Grey zones, both elevated, or conflicting risks → uncertain.
    if p_hw >= hw_accept and p_nt >= nt_accept:
        return _uncertain(HandwritingDecisionReason.THRESHOLD_CONFLICT)
    return _uncertain(HandwritingDecisionReason.LOW_TOP_PROBABILITY)
