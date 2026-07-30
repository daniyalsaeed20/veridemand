"""Deterministic Phase 5 routing decisions from three-class model scores."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from backend.app.contracts.ocr import (
    HandwritingClassificationLifecycle,
    HandwritingClassificationOutcome,
    HandwritingDecisionReason,
    HandwritingInferenceSource,
)
from backend.app.extraction.handwriting_router.constants import EXPECTED_MODEL_LABELS


@dataclass(frozen=True, slots=True)
class RoutingThresholds:
    printed: float
    handwritten: float
    non_text: float
    minimum_class_margin: float


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


def _finite_scores(scores: np.ndarray) -> bool:
    return bool(scores.shape == (3,) and np.all(np.isfinite(scores)))


def decide_routing_outcome(
    scores: np.ndarray | list[float] | tuple[float, ...],
    thresholds: RoutingThresholds,
    *,
    labels: tuple[str, str, str] = EXPECTED_MODEL_LABELS,
) -> RoutingDecision:
    """Map three class scores to a public routing outcome.

    Safety direction: when in doubt, return ``uncertain``. Never default invalid
    output to ``printed``.
    """

    arr = np.asarray(scores, dtype=np.float64).reshape(-1)
    empty_scores = {label: float("nan") for label in labels}
    if arr.shape != (3,) or not _finite_scores(arr):
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
    if np.any(arr < -1e-9):
        return RoutingDecision(
            lifecycle=HandwritingClassificationLifecycle.FAILED,
            outcome=HandwritingClassificationOutcome.UNCERTAIN,
            decision_reason=HandwritingDecisionReason.INVALID_OUTPUT,
            inference_source=HandwritingInferenceSource.SAFETY_ABSTENTION,
            top_class=None,
            top_score=None,
            second_score=None,
            class_margin=None,
            class_scores={labels[i]: float(arr[i]) for i in range(3)},
        )

    order = np.argsort(-arr)
    top_i = int(order[0])
    second_i = int(order[1])
    top_score = float(arr[top_i])
    second_score = float(arr[second_i])
    margin = top_score - second_score
    score_map = {labels[i]: float(arr[i]) for i in range(3)}
    thr = {
        "printed": thresholds.printed,
        "handwritten": thresholds.handwritten,
        "non_text": thresholds.non_text,
    }
    passed = [labels[i] for i in range(3) if float(arr[i]) >= thr[labels[i]]]

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
            top_class=labels[top_i],
            top_score=top_score,
            second_score=second_score,
            class_margin=margin,
            class_scores=score_map,
        )

    if abs(top_score - second_score) < 1e-12:
        return _uncertain(HandwritingDecisionReason.THRESHOLD_CONFLICT)
    if not passed:
        return _uncertain(HandwritingDecisionReason.LOW_TOP_PROBABILITY)
    if len(passed) >= 2:
        return _uncertain(HandwritingDecisionReason.THRESHOLD_CONFLICT)
    if margin < thresholds.minimum_class_margin:
        return _uncertain(HandwritingDecisionReason.LOW_CLASS_MARGIN)

    winner = passed[0]
    if winner != labels[top_i]:
        return _uncertain(HandwritingDecisionReason.THRESHOLD_CONFLICT)

    reason_map = {
        "printed": HandwritingDecisionReason.PRINTED_THRESHOLD_MET,
        "handwritten": HandwritingDecisionReason.HANDWRITING_THRESHOLD_MET,
        "non_text": HandwritingDecisionReason.NON_TEXT_THRESHOLD_MET,
    }
    outcome_map = {
        "printed": HandwritingClassificationOutcome.PRINTED,
        "handwritten": HandwritingClassificationOutcome.HANDWRITTEN,
        "non_text": HandwritingClassificationOutcome.NON_TEXT,
    }
    return RoutingDecision(
        lifecycle=HandwritingClassificationLifecycle.CLASSIFIED,
        outcome=outcome_map[winner],
        decision_reason=reason_map[winner],
        inference_source=HandwritingInferenceSource.MODEL_INFERENCE,
        top_class=winner,
        top_score=top_score,
        second_score=second_score,
        class_margin=margin,
        class_scores=score_map,
    )
