"""Lexicographic prototype threshold search on OOF predictions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from backend.app.extraction.handwriting_router.routing import (
    RoutingThresholds,
    decide_routing_outcome,
)

from model_development.handwriting_classifier import THRESHOLD_SET_VERSION
from model_development.handwriting_classifier.config import (
    CLASS_ORDER,
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
    printed: float
    handwritten: float
    non_text: float
    minimum_class_margin: float
    handwritten_to_printed: int
    nontext_to_printed: int
    handwriting_safe_bypass_recall: float
    printed_retention_recall: float
    unnecessary_uncertain_rate: float
    handwriting_class_recall_pre_abstention: float
    overall_uncertain_rate: float
    passes_safety_gate: bool
    routed_counts: dict[str, int]
    slice_gates: dict[str, Any]
    passes_slice_gates: bool

    def sort_key(self) -> tuple[Any, ...]:
        # Lexicographic: safety first (incl. slices), then quality.
        return (
            0 if self.passes_safety_gate else 1,
            0 if self.passes_slice_gates else 1,
            self.handwritten_to_printed,
            self.nontext_to_printed,
            -self.handwriting_safe_bypass_recall,
            -self.printed_retention_recall,
            -self.handwriting_class_recall_pre_abstention,
            self.unnecessary_uncertain_rate,
        )


def route_probabilities(
    probs: Sequence[float],
    thresholds: RoutingThresholds | ThresholdCandidate,
) -> str:
    if isinstance(thresholds, ThresholdCandidate):
        thr = RoutingThresholds(
            printed=thresholds.printed,
            handwritten=thresholds.handwritten,
            non_text=thresholds.non_text,
            minimum_class_margin=thresholds.minimum_class_margin,
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
        outcome = route_probabilities(p["probabilities"], candidate)
        for name in HANDWRITING_SLICES:
            # hand_printed may appear as hand_printed or hand-printed
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
        "passes_slice_gates": passes,
    }


def evaluate_thresholds(
    predictions: Sequence[dict[str, Any]],
    candidate: ThresholdCandidate,
) -> ThresholdMetrics:
    """Evaluate one threshold set on project OOF predictions (no synthetic/public)."""

    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    hw = [p for p in project if p["label"] == "handwritten"]
    printed = [p for p in project if p["label"] == "printed"]

    routed: dict[str, int] = {
        "printed": 0,
        "handwritten": 0,
        "non_text": 0,
        "uncertain": 0,
    }
    hw_to_printed = 0
    nt_to_printed = 0
    hw_safe = 0
    printed_retained = 0
    printed_uncertain = 0
    hw_argmax_correct = 0

    for p in project:
        outcome = route_probabilities(p["probabilities"], candidate)
        routed[outcome] = routed.get(outcome, 0) + 1
        argmax = CLASS_ORDER[int(np.argmax(p["probabilities"]))]
        if p["label"] == "handwritten":
            if argmax == "handwritten":
                hw_argmax_correct += 1
            if outcome == "printed":
                hw_to_printed += 1
            if outcome in ("handwritten", "uncertain"):
                hw_safe += 1
        elif p["label"] == "non_text":
            if outcome == "printed":
                nt_to_printed += 1
        elif p["label"] == "printed":
            if outcome == "printed":
                printed_retained += 1
            if outcome == "uncertain":
                printed_uncertain += 1

    hw_n = max(len(hw), 1)
    pr_n = max(len(printed), 1)
    safe_bypass = hw_safe / hw_n if hw else 1.0
    printed_ret = printed_retained / pr_n if printed else 1.0
    unnecessary = printed_uncertain / pr_n if printed else 0.0
    overall_unc = routed.get("uncertain", 0) / max(len(project), 1)
    hw_recall_pre = hw_argmax_correct / hw_n if hw else 1.0

    slice_info = evaluate_handwriting_slices(project, candidate)
    passes_slices = bool(slice_info["passes_slice_gates"])

    passes = (
        hw_to_printed == 0
        and nt_to_printed == 0
        and abs(safe_bypass - 1.0) < 1e-12
        and printed_ret >= 0.80
        and passes_slices
    )
    return ThresholdMetrics(
        printed=candidate.printed,
        handwritten=candidate.handwritten,
        non_text=candidate.non_text,
        minimum_class_margin=candidate.minimum_class_margin,
        handwritten_to_printed=hw_to_printed,
        nontext_to_printed=nt_to_printed,
        handwriting_safe_bypass_recall=safe_bypass,
        printed_retention_recall=printed_ret,
        unnecessary_uncertain_rate=unnecessary,
        handwriting_class_recall_pre_abstention=hw_recall_pre,
        overall_uncertain_rate=overall_unc,
        passes_safety_gate=passes,
        routed_counts=routed,
        slice_gates=slice_info,
        passes_slice_gates=passes_slices,
    )


def search_thresholds(
    predictions: Sequence[dict[str, Any]],
    grid: Sequence[ThresholdCandidate] | None = None,
) -> tuple[ThresholdMetrics | None, list[ThresholdMetrics]]:
    """Deterministic bounded search; return best + Pareto-ish top candidates."""

    candidates = list(grid) if grid is not None else default_threshold_grid()
    scored = [evaluate_thresholds(predictions, c) for c in candidates]
    scored.sort(key=lambda m: m.sort_key())
    passing = [m for m in scored if m.passes_safety_gate]
    selected = passing[0] if passing else None
    return selected, scored[:20]


def thresholds_to_dict(m: ThresholdMetrics | None) -> dict[str, Any] | None:
    if m is None:
        return None
    return {
        "threshold_set_version": THRESHOLD_SET_VERSION,
        "printed": m.printed,
        "handwritten": m.handwritten,
        "non_text": m.non_text,
        "minimum_class_margin": m.minimum_class_margin,
        "handwritten_to_printed": m.handwritten_to_printed,
        "nontext_to_printed": m.nontext_to_printed,
        "handwriting_safe_bypass_recall": m.handwriting_safe_bypass_recall,
        "printed_retention_recall": m.printed_retention_recall,
        "unnecessary_uncertain_rate": m.unnecessary_uncertain_rate,
        "handwriting_class_recall_pre_abstention": m.handwriting_class_recall_pre_abstention,
        "overall_uncertain_rate": m.overall_uncertain_rate,
        "passes_safety_gate": m.passes_safety_gate,
        "passes_slice_gates": m.passes_slice_gates,
        "routed_counts": m.routed_counts,
        "slice_gates": m.slice_gates,
    }


def challenge_routing_report(
    predictions: Sequence[dict[str, Any]],
    thresholds: ThresholdCandidate | ThresholdMetrics,
) -> dict[str, int]:
    cand: ThresholdCandidate
    if isinstance(thresholds, ThresholdMetrics):
        cand = ThresholdCandidate(
            printed=thresholds.printed,
            handwritten=thresholds.handwritten,
            non_text=thresholds.non_text,
            minimum_class_margin=thresholds.minimum_class_margin,
        )
    else:
        cand = thresholds
    counts = {"printed": 0, "handwritten": 0, "non_text": 0, "uncertain": 0}
    for p in predictions:
        outcome = route_probabilities(p["probabilities"], cand)
        counts[outcome] = counts.get(outcome, 0) + 1
    return counts
