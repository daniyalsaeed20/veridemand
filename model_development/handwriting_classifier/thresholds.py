"""Lexicographic route-first threshold search on project OOF predictions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from backend.app.extraction.handwriting_router.routing import (
    RoutingThresholds,
    decide_routing_outcome,
)

from model_development.handwriting_classifier import THRESHOLD_SET_VERSION, TRAINING_LABELS
from model_development.handwriting_classifier.config import (
    ThresholdCandidate,
    default_threshold_grid,
)

HANDWRITING_SLICES = (
    "digits",
    "hand_printed",
    "cursive",
    "signature",
    "longer_note",
)


@dataclass(frozen=True)
class ThresholdMetrics:
    local_ocr_safe_threshold: float
    vision_required_threshold: float
    handwriting_accept_threshold: float
    handwritten_to_printed: int
    uncertain_to_printed: int
    nontext_to_printed: int
    handwriting_safe_bypass_recall: float
    uncertain_safe_bypass_recall: float
    printed_retention_recall: float
    direct_handwritten_rate: float
    overall_uncertain_rate: float
    overall_reserved_for_vision_rate: float
    handwriting_grey_zone_rate: float
    cursive_to_printed: int
    signature_to_printed: int
    passes_safety_gate: bool
    routed_counts: dict[str, int]
    slice_gates: dict[str, Any]
    passes_slice_gates: bool

    def sort_key(self) -> tuple[Any, ...]:
        """Lexicographic objective (Task B4 §9)."""

        return (
            self.handwritten_to_printed,  # 1. = 0
            self.uncertain_to_printed,  # 2. = 0
            self.nontext_to_printed,  # 3. = 0
            self.cursive_to_printed,  # 4. = 0
            self.signature_to_printed,  # 5. = 0
            0 if self.printed_retention_recall >= 0.80 else 1,  # 6. gate
            -self.printed_retention_recall,  # 6b. maximise retention
            -self.direct_handwritten_rate,  # 7
            self.overall_uncertain_rate,  # 8 minimise unnecessary uncertainty
            0 if self.passes_safety_gate else 1,
        )


def route_probabilities(
    probs: Sequence[float],
    thresholds: RoutingThresholds | ThresholdCandidate,
) -> str:
    if isinstance(thresholds, ThresholdCandidate):
        thr = RoutingThresholds(
            local_ocr_safe_threshold=thresholds.local_ocr_safe_threshold,
            vision_required_threshold=thresholds.vision_required_threshold,
            handwriting_accept_threshold=thresholds.handwriting_accept_threshold,
        )
    else:
        thr = thresholds
    decision = decide_routing_outcome(np.asarray(probs, dtype=np.float64), thr)
    return decision.outcome.value


def _category_tags(source_category: object) -> set[str]:
    if not isinstance(source_category, str) or not source_category:
        return set()
    return {p.strip() for p in source_category.split(",") if p.strip()}


def evaluate_handwriting_slices(
    predictions: Sequence[dict[str, Any]],
    candidate: ThresholdCandidate,
) -> dict[str, Any]:
    """Per-slice routed outcomes for project handwriting seeds."""

    slices: dict[str, dict[str, int]] = {
        name: {"printed": 0, "handwritten": 0, "uncertain": 0, "non_text": 0, "support": 0}
        for name in HANDWRITING_SLICES
    }
    for p in predictions:
        if p.get("synthetic") or p.get("public"):
            continue
        if p.get("label") != "handwritten":
            continue
        tags = _category_tags(p.get("source_category"))
        probs = (
            p.get("route_probabilities") or p.get("risk_probabilities") or p.get("probabilities")
        )
        outcome = route_probabilities(probs, candidate)
        for name in HANDWRITING_SLICES:
            aliases = {name, name.replace("_", "-")}
            if name == "hand_printed":
                aliases.add("handprinted")
            if tags & aliases:
                slices[name]["support"] += 1
                slices[name][outcome] = slices[name].get(outcome, 0) + 1

    cursive_printed = int(slices["cursive"]["printed"])
    sig_printed = int(slices["signature"]["printed"])
    # Model never emits non_text; unsafe = routed to printed only.
    passes = cursive_printed == 0 and sig_printed == 0
    return {
        "slices": slices,
        "cursive_routed_printed": cursive_printed,
        "signature_routed_printed": sig_printed,
        "cursive_to_printed": cursive_printed,
        "signature_to_printed": sig_printed,
        "passes_slice_gates": passes,
    }


def evaluate_thresholds(
    predictions: Sequence[dict[str, Any]],
    candidate: ThresholdCandidate,
) -> ThresholdMetrics:
    """Evaluate one threshold set on project OOF predictions (no synthetic/public)."""

    if not candidate.is_ordered():
        raise ValueError("Threshold candidate violates local_ocr_safe < vision_required")

    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    hw = [p for p in project if p["label"] == "handwritten"]
    printed = [p for p in project if p["label"] == "printed"]
    uncertain = [p for p in project if p["label"] == "uncertain"]

    routed: dict[str, int] = {
        "printed": 0,
        "handwritten": 0,
        "non_text": 0,
        "uncertain": 0,
    }
    hw_to_printed = 0
    unc_to_printed = 0
    nt_to_printed = 0
    hw_safe = 0
    unc_safe = 0
    printed_retained = 0
    hw_grey = 0
    reserved = 0

    for p in project:
        probs = (
            p.get("route_probabilities") or p.get("risk_probabilities") or p.get("probabilities")
        )
        outcome = route_probabilities(probs, candidate)
        routed[outcome] = routed.get(outcome, 0) + 1
        if outcome in ("handwritten", "uncertain"):
            reserved += 1
        p_route = float(probs[0])
        if p["label"] == "handwritten":
            if outcome == "printed":
                hw_to_printed += 1
            if outcome in ("handwritten", "uncertain"):
                hw_safe += 1
            if candidate.local_ocr_safe_threshold < p_route < candidate.vision_required_threshold:
                hw_grey += 1
        elif p["label"] == "uncertain":
            if outcome == "printed":
                unc_to_printed += 1
            if outcome in ("handwritten", "uncertain"):
                unc_safe += 1
        elif p["label"] == "non_text":
            if outcome == "printed":
                nt_to_printed += 1
        elif p["label"] == "printed":
            if outcome == "printed":
                printed_retained += 1

    hw_n = max(len(hw), 1)
    pr_n = max(len(printed), 1)
    unc_n = max(len(uncertain), 1)
    safe_bypass = hw_safe / hw_n if hw else 1.0
    unc_bypass = unc_safe / unc_n if uncertain else 1.0
    printed_ret = printed_retained / pr_n if printed else 1.0
    overall_unc = routed.get("uncertain", 0) / max(len(project), 1)
    reserved_rate = reserved / max(len(project), 1)
    direct_hw = (
        sum(
            1
            for p in hw
            if route_probabilities(
                p.get("route_probabilities") or p.get("risk_probabilities") or p["probabilities"],
                candidate,
            )
            == "handwritten"
        )
        / hw_n
        if hw
        else 0.0
    )
    hw_grey_rate = hw_grey / hw_n if hw else 0.0

    slice_info = evaluate_handwriting_slices(project, candidate)
    passes_slices = bool(slice_info["passes_slice_gates"])
    cursive_printed = int(slice_info["cursive_to_printed"])
    signature_printed = int(slice_info["signature_to_printed"])

    passes = (
        hw_to_printed == 0
        and unc_to_printed == 0
        and nt_to_printed == 0
        and cursive_printed == 0
        and signature_printed == 0
        and abs(safe_bypass - 1.0) < 1e-12
        and abs(unc_bypass - 1.0) < 1e-12
        and printed_ret >= 0.80
        and passes_slices
    )
    return ThresholdMetrics(
        local_ocr_safe_threshold=candidate.local_ocr_safe_threshold,
        vision_required_threshold=candidate.vision_required_threshold,
        handwriting_accept_threshold=candidate.handwriting_accept_threshold,
        handwritten_to_printed=hw_to_printed,
        uncertain_to_printed=unc_to_printed,
        nontext_to_printed=nt_to_printed,
        handwriting_safe_bypass_recall=safe_bypass,
        uncertain_safe_bypass_recall=unc_bypass,
        printed_retention_recall=printed_ret,
        direct_handwritten_rate=direct_hw,
        overall_uncertain_rate=overall_unc,
        overall_reserved_for_vision_rate=reserved_rate,
        handwriting_grey_zone_rate=hw_grey_rate,
        cursive_to_printed=cursive_printed,
        signature_to_printed=signature_printed,
        passes_safety_gate=passes,
        routed_counts=routed,
        slice_gates=slice_info,
        passes_slice_gates=passes_slices,
    )


def search_thresholds(
    predictions: Sequence[dict[str, Any]],
    grid: Sequence[ThresholdCandidate] | None = None,
) -> tuple[ThresholdMetrics | None, list[ThresholdMetrics]]:
    """Deterministic bounded search; return best passing candidate + top scored."""

    candidates = list(grid) if grid is not None else default_threshold_grid()
    scored = [evaluate_thresholds(predictions, c) for c in candidates if c.is_ordered()]
    scored.sort(key=lambda m: m.sort_key())
    passing = [m for m in scored if m.passes_safety_gate]
    selected = passing[0] if passing else None
    return selected, scored[:20]


def thresholds_to_dict(m: ThresholdMetrics | None) -> dict[str, Any] | None:
    if m is None:
        return None
    return {
        "threshold_set_version": THRESHOLD_SET_VERSION,
        "local_ocr_safe_threshold": m.local_ocr_safe_threshold,
        "vision_required_threshold": m.vision_required_threshold,
        "handwriting_accept_threshold": m.handwriting_accept_threshold,
        "handwritten_to_printed": m.handwritten_to_printed,
        "uncertain_to_printed": m.uncertain_to_printed,
        "nontext_to_printed": m.nontext_to_printed,
        "handwriting_safe_bypass_recall": m.handwriting_safe_bypass_recall,
        "uncertain_safe_bypass_recall": m.uncertain_safe_bypass_recall,
        "printed_retention_recall": m.printed_retention_recall,
        "direct_handwritten_rate": m.direct_handwritten_rate,
        "overall_uncertain_rate": m.overall_uncertain_rate,
        "overall_reserved_for_vision_rate": m.overall_reserved_for_vision_rate,
        "handwriting_grey_zone_rate": m.handwriting_grey_zone_rate,
        "cursive_to_printed": m.cursive_to_printed,
        "signature_to_printed": m.signature_to_printed,
        "passes_safety_gate": m.passes_safety_gate,
        "passes_slice_gates": m.passes_slice_gates,
        "routed_counts": m.routed_counts,
        "slice_gates": m.slice_gates,
        "training_labels": list(TRAINING_LABELS),
    }


def challenge_routing_report(
    predictions: Sequence[dict[str, Any]],
    thresholds: ThresholdCandidate | ThresholdMetrics,
) -> dict[str, int]:
    cand: ThresholdCandidate
    if isinstance(thresholds, ThresholdMetrics):
        cand = ThresholdCandidate(
            local_ocr_safe_threshold=thresholds.local_ocr_safe_threshold,
            vision_required_threshold=thresholds.vision_required_threshold,
            handwriting_accept_threshold=thresholds.handwriting_accept_threshold,
        )
    else:
        cand = thresholds
    counts = {"printed": 0, "handwritten": 0, "non_text": 0, "uncertain": 0}
    for p in predictions:
        probs = (
            p.get("route_probabilities") or p.get("risk_probabilities") or p.get("probabilities")
        )
        outcome = route_probabilities(probs, cand)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def to_routing_thresholds(m: ThresholdMetrics | ThresholdCandidate) -> RoutingThresholds:
    if isinstance(m, ThresholdMetrics):
        return RoutingThresholds(
            local_ocr_safe_threshold=m.local_ocr_safe_threshold,
            vision_required_threshold=m.vision_required_threshold,
            handwriting_accept_threshold=m.handwriting_accept_threshold,
        )
    return RoutingThresholds(
        local_ocr_safe_threshold=m.local_ocr_safe_threshold,
        vision_required_threshold=m.vision_required_threshold,
        handwriting_accept_threshold=m.handwriting_accept_threshold,
    )
