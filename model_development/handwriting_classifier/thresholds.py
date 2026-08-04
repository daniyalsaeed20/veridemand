"""Lexicographic dual-risk threshold search on project OOF predictions."""

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
    handwriting_accept_threshold: float
    handwriting_safe_low_threshold: float
    non_text_accept_threshold: float
    non_text_safe_low_threshold: float
    handwritten_to_printed: int
    handwritten_to_nontext: int
    nontext_to_printed: int
    handwriting_safe_bypass_recall: float
    printed_retention_recall: float
    direct_handwritten_rate: float
    direct_nontext_rate: float
    overall_uncertain_rate: float
    handwriting_grey_zone_rate: float
    cursive_unsafe: int
    signature_unsafe: int
    passes_safety_gate: bool
    routed_counts: dict[str, int]
    slice_gates: dict[str, Any]
    passes_slice_gates: bool

    def sort_key(self) -> tuple[Any, ...]:
        """Lexicographic objective (Task B3 §14.1)."""

        return (
            self.handwritten_to_printed,  # 1. = 0 preferred
            self.handwritten_to_nontext,  # 2. = 0
            self.cursive_unsafe,  # 3. = 0
            self.signature_unsafe,  # 4. = 0
            -self.handwriting_safe_bypass_recall,  # 5. = 100%
            self.nontext_to_printed,  # 6. = 0
            0 if self.printed_retention_recall >= 0.80 else 1,  # 7. gate
            -self.printed_retention_recall,  # 7b. maximise retention
            -self.direct_handwritten_rate,  # 8
            -self.direct_nontext_rate,  # 9
            self.overall_uncertain_rate,  # 10 minimise after safety
            0 if self.passes_safety_gate else 1,
        )


def route_probabilities(
    probs: Sequence[float],
    thresholds: RoutingThresholds | ThresholdCandidate,
) -> str:
    if isinstance(thresholds, ThresholdCandidate):
        thr = RoutingThresholds(
            handwriting_accept_threshold=thresholds.handwriting_accept_threshold,
            handwriting_safe_low_threshold=thresholds.handwriting_safe_low_threshold,
            non_text_accept_threshold=thresholds.non_text_accept_threshold,
            non_text_safe_low_threshold=thresholds.non_text_safe_low_threshold,
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
        probs = p.get("risk_probabilities") or p.get("probabilities")
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
    cursive_non_text = int(slices["cursive"]["non_text"])
    sig_non_text = int(slices["signature"]["non_text"])
    passes = (
        cursive_printed == 0 and sig_printed == 0 and cursive_non_text == 0 and sig_non_text == 0
    )
    return {
        "slices": slices,
        "cursive_routed_printed": cursive_printed,
        "signature_routed_printed": sig_printed,
        "cursive_routed_non_text": cursive_non_text,
        "signature_routed_non_text": sig_non_text,
        "cursive_unsafe": cursive_printed + cursive_non_text,
        "signature_unsafe": sig_printed + sig_non_text,
        "passes_slice_gates": passes,
    }


def evaluate_thresholds(
    predictions: Sequence[dict[str, Any]],
    candidate: ThresholdCandidate,
) -> ThresholdMetrics:
    """Evaluate one threshold set on project OOF predictions (no synthetic/public)."""

    if not candidate.is_ordered():
        raise ValueError("Threshold candidate violates safe_low < accept ordering")

    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    hw = [p for p in project if p["label"] == "handwritten"]
    printed = [p for p in project if p["label"] == "printed"]
    nt = [p for p in project if p["label"] == "non_text"]

    routed: dict[str, int] = {
        "printed": 0,
        "handwritten": 0,
        "non_text": 0,
        "uncertain": 0,
    }
    hw_to_printed = 0
    hw_to_nontext = 0
    nt_to_printed = 0
    hw_safe = 0
    printed_retained = 0
    hw_grey = 0

    for p in project:
        probs = p.get("risk_probabilities") or p.get("probabilities")
        outcome = route_probabilities(probs, candidate)
        routed[outcome] = routed.get(outcome, 0) + 1
        p_hw = float(probs[0])
        if p["label"] == "handwritten":
            if outcome == "printed":
                hw_to_printed += 1
            if outcome == "non_text":
                hw_to_nontext += 1
            if outcome in ("handwritten", "uncertain"):
                hw_safe += 1
            if (
                candidate.handwriting_safe_low_threshold
                < p_hw
                < candidate.handwriting_accept_threshold
            ):
                hw_grey += 1
        elif p["label"] == "non_text":
            if outcome == "printed":
                nt_to_printed += 1
        elif p["label"] == "printed":
            if outcome == "printed":
                printed_retained += 1

    hw_n = max(len(hw), 1)
    pr_n = max(len(printed), 1)
    safe_bypass = hw_safe / hw_n if hw else 1.0
    printed_ret = printed_retained / pr_n if printed else 1.0
    overall_unc = routed.get("uncertain", 0) / max(len(project), 1)
    direct_hw = routed.get("handwritten", 0) / hw_n if hw else 0.0
    direct_nt = (
        sum(
            1
            for p in nt
            if route_probabilities(p.get("risk_probabilities") or p["probabilities"], candidate)
            == "non_text"
        )
        / max(len(nt), 1)
        if nt
        else 0.0
    )
    hw_grey_rate = hw_grey / hw_n if hw else 0.0

    slice_info = evaluate_handwriting_slices(project, candidate)
    passes_slices = bool(slice_info["passes_slice_gates"])
    cursive_unsafe = int(slice_info["cursive_unsafe"])
    signature_unsafe = int(slice_info["signature_unsafe"])

    passes = (
        hw_to_printed == 0
        and hw_to_nontext == 0
        and abs(safe_bypass - 1.0) < 1e-12
        and cursive_unsafe == 0
        and signature_unsafe == 0
        and nt_to_printed == 0
        and printed_ret >= 0.80
        and passes_slices
    )
    return ThresholdMetrics(
        handwriting_accept_threshold=candidate.handwriting_accept_threshold,
        handwriting_safe_low_threshold=candidate.handwriting_safe_low_threshold,
        non_text_accept_threshold=candidate.non_text_accept_threshold,
        non_text_safe_low_threshold=candidate.non_text_safe_low_threshold,
        handwritten_to_printed=hw_to_printed,
        handwritten_to_nontext=hw_to_nontext,
        nontext_to_printed=nt_to_printed,
        handwriting_safe_bypass_recall=safe_bypass,
        printed_retention_recall=printed_ret,
        direct_handwritten_rate=direct_hw,
        direct_nontext_rate=direct_nt,
        overall_uncertain_rate=overall_unc,
        handwriting_grey_zone_rate=hw_grey_rate,
        cursive_unsafe=cursive_unsafe,
        signature_unsafe=signature_unsafe,
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
    # If none pass, still return best-by-sort for diagnostics (not selected).
    return selected, scored[:20]


def thresholds_to_dict(m: ThresholdMetrics | None) -> dict[str, Any] | None:
    if m is None:
        return None
    return {
        "threshold_set_version": THRESHOLD_SET_VERSION,
        "handwriting_accept_threshold": m.handwriting_accept_threshold,
        "handwriting_safe_low_threshold": m.handwriting_safe_low_threshold,
        "non_text_accept_threshold": m.non_text_accept_threshold,
        "non_text_safe_low_threshold": m.non_text_safe_low_threshold,
        "handwritten_to_printed": m.handwritten_to_printed,
        "handwritten_to_nontext": m.handwritten_to_nontext,
        "nontext_to_printed": m.nontext_to_printed,
        "handwriting_safe_bypass_recall": m.handwriting_safe_bypass_recall,
        "printed_retention_recall": m.printed_retention_recall,
        "direct_handwritten_rate": m.direct_handwritten_rate,
        "direct_nontext_rate": m.direct_nontext_rate,
        "overall_uncertain_rate": m.overall_uncertain_rate,
        "handwriting_grey_zone_rate": m.handwriting_grey_zone_rate,
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
            handwriting_accept_threshold=thresholds.handwriting_accept_threshold,
            handwriting_safe_low_threshold=thresholds.handwriting_safe_low_threshold,
            non_text_accept_threshold=thresholds.non_text_accept_threshold,
            non_text_safe_low_threshold=thresholds.non_text_safe_low_threshold,
        )
    else:
        cand = thresholds
    counts = {"printed": 0, "handwritten": 0, "non_text": 0, "uncertain": 0}
    for p in predictions:
        probs = p.get("risk_probabilities") or p.get("probabilities")
        outcome = route_probabilities(probs, cand)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts


def to_routing_thresholds(m: ThresholdMetrics | ThresholdCandidate) -> RoutingThresholds:
    if isinstance(m, ThresholdMetrics):
        return RoutingThresholds(
            handwriting_accept_threshold=m.handwriting_accept_threshold,
            handwriting_safe_low_threshold=m.handwriting_safe_low_threshold,
            non_text_accept_threshold=m.non_text_accept_threshold,
            non_text_safe_low_threshold=m.non_text_safe_low_threshold,
        )
    return RoutingThresholds(
        handwriting_accept_threshold=m.handwriting_accept_threshold,
        handwriting_safe_low_threshold=m.handwriting_safe_low_threshold,
        non_text_accept_threshold=m.non_text_accept_threshold,
        non_text_safe_low_threshold=m.non_text_safe_low_threshold,
    )
