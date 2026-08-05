"""Aggregate OOF metrics for route-first heads and public routing (privacy-safe)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np

from model_development.handwriting_classifier import TRAINING_LABELS
from model_development.handwriting_classifier.config import route_target_and_mask


def route_head_metrics(predictions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Binary metrics per route head using 0.5 decision on sigmoid probs (diagnostic)."""

    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    route_y: list[float] = []
    route_p: list[float] = []
    hw_y: list[float] = []
    hw_p: list[float] = []
    for p in project:
        label = p["label"]
        probs = (
            p.get("route_probabilities") or p.get("risk_probabilities") or p.get("probabilities")
        )
        vision, hw, mask = route_target_and_mask(label)
        route_y.append(vision)
        route_p.append(float(probs[0]))
        if mask > 0.5:
            hw_y.append(hw)
            hw_p.append(float(probs[1]))

    def _binary(y: list[float], p: list[float]) -> dict[str, float]:
        if not y:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support_pos": 0.0}
        pred = [1.0 if v >= 0.5 else 0.0 for v in p]
        tp = sum(1 for yi, pi in zip(y, pred, strict=True) if yi == 1 and pi == 1)
        fp = sum(1 for yi, pi in zip(y, pred, strict=True) if yi == 0 and pi == 1)
        fn = sum(1 for yi, pi in zip(y, pred, strict=True) if yi == 1 and pi == 0)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        return {
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "support_pos": float(sum(y)),
        }

    return {
        "vision_required": _binary(route_y, route_p),
        "handwriting_present": _binary(hw_y, hw_p),
    }


# Back-compat alias.
risk_head_metrics = route_head_metrics


def public_routing_matrix(
    predictions: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Confusion-style matrix from human labels to public routed outcomes."""

    labels = list(TRAINING_LABELS)
    outcomes = ["printed", "handwritten", "uncertain", "non_text"]
    index_t = {lab: i for i, lab in enumerate(labels)}
    index_o = {lab: i for i, lab in enumerate(outcomes)}
    mat = np.zeros((len(labels), len(outcomes)), dtype=np.int64)
    for p in predictions:
        if p.get("synthetic") or p.get("public"):
            continue
        true = p["label"]
        if true not in index_t:
            continue
        outcome = p.get("routed_outcome")
        if outcome is None:
            continue
        if outcome not in index_o:
            continue
        mat[index_t[true], index_o[outcome]] += 1
    return {"true_labels": labels, "outcomes": outcomes, "matrix": mat.tolist()}


def fold_support(predictions: Sequence[dict[str, Any]]) -> dict[str, int]:
    c = Counter(p["label"] for p in predictions if not p.get("synthetic"))
    return {lab: int(c.get(lab, 0)) for lab in TRAINING_LABELS}


def summarize_oof(predictions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    return {
        "kind": "source-group-isolated out-of-fold prototype diagnostics",
        "n_examples": len(project),
        "class_support": fold_support(project),
        "route_head_metrics": route_head_metrics(project),
        "risk_head_metrics": route_head_metrics(project),  # back-compat key
        "public_routing_matrix": public_routing_matrix(project),
    }


def opaque_error_categories(
    predictions: Sequence[dict[str, Any]],
    *,
    routed: Sequence[dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Aggregate FP/FN style categories without private IDs."""

    rows = routed if routed is not None else predictions
    cats: Counter[str] = Counter()
    for p in rows:
        if p.get("synthetic") or p.get("public"):
            continue
        true = p["label"]
        outcome = p.get("routed_outcome")
        if outcome is None:
            continue
        if true == "handwritten" and outcome == "printed":
            cats["handwritten_routed_printed"] += 1
        if true == "uncertain" and outcome == "printed":
            cats["uncertain_routed_printed"] += 1
        if true == "handwritten" and outcome == "non_text":
            cats["handwritten_routed_non_text"] += 1
        if true == "printed" and outcome == "handwritten":
            cats["printed_routed_handwritten"] += 1
        if true == "printed" and outcome == "uncertain":
            cats["printed_routed_uncertain"] += 1
        if true == "non_text" and outcome == "printed":
            cats["non_text_routed_printed"] += 1
        cats_src = (
            (p.get("source_category") or "") if isinstance(p.get("source_category"), str) else ""
        )
        if true == "handwritten":
            if "signature" in cats_src and outcome not in ("handwritten", "uncertain"):
                cats["signatures_confused"] += 1
            if "digits" in cats_src and outcome not in ("handwritten", "uncertain"):
                cats["handwritten_digits_confused"] += 1
            if "cursive" in cats_src and outcome not in ("handwritten", "uncertain"):
                cats["cursive_confused"] += 1
        w = int(p.get("width") or 0)
        h = int(p.get("height") or 0)
        if w and h and w * h < 40 * 40 and outcome != true:
            cats["small_crops_confused"] += 1
        if w and h and max(w, h) / max(min(w, h), 1) > 8 and outcome != true:
            cats["broad_crops_confused"] += 1
    return dict(cats)
