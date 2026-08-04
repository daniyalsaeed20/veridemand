"""Aggregate OOF metrics for dual-risk heads and public routing (privacy-safe)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np

from model_development.handwriting_classifier import TRAINING_LABELS


def risk_head_metrics(predictions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Binary metrics per risk head using 0.5 decision on sigmoid probs (diagnostic)."""

    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    hw_y = []
    hw_p = []
    nt_y = []
    nt_p = []
    for p in project:
        label = p["label"]
        probs = p.get("risk_probabilities") or p.get("probabilities")
        hw_y.append(1.0 if label == "handwritten" else 0.0)
        nt_y.append(1.0 if label == "non_text" else 0.0)
        hw_p.append(float(probs[0]))
        nt_p.append(float(probs[1]))

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
        "handwriting_risk": _binary(hw_y, hw_p),
        "non_text_risk": _binary(nt_y, nt_p),
    }


def public_routing_matrix(
    predictions: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Confusion-style matrix from human labels to public routed outcomes."""

    labels = list(TRAINING_LABELS)
    outcomes = ["printed", "handwritten", "uncertain", "non_text"]
    index_t = {lab: i for i, lab in enumerate(labels)}
    index_o = {lab: i for i, lab in enumerate(outcomes)}
    mat = np.zeros((3, 4), dtype=np.int64)
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


def confusion_matrix(
    predictions: Sequence[dict[str, Any]],
    *,
    use_argmax: bool = True,
) -> dict[str, Any]:
    """Legacy 3x3 helper: maps dual-risk probs to a forced argmax class for diagnostics.

    Argmax over [1-max(p_hw,p_nt), p_hw, p_nt] approximates printed/hw/non_text.
    Prefer ``public_routing_matrix`` for safety evaluation.
    """

    labels = list(TRAINING_LABELS)
    index = {lab: i for i, lab in enumerate(labels)}
    mat = np.zeros((3, 3), dtype=np.int64)
    for p in predictions:
        if p.get("synthetic") or p.get("public"):
            continue
        true = p["label"]
        if true not in index:
            continue
        if use_argmax:
            probs = p.get("risk_probabilities") or p.get("probabilities")
            p_hw = float(probs[0])
            p_nt = float(probs[1])
            scores = [1.0 - max(p_hw, p_nt), p_hw, p_nt]
            pred = labels[int(np.argmax(scores))]
        else:
            pred = p.get("routed_outcome")
            if pred not in index:
                continue
        mat[index[true], index[pred]] += 1
    return {"labels": labels, "matrix": mat.tolist()}


def per_class_prf(predictions: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    cm = confusion_matrix(predictions)["matrix"]
    out: dict[str, dict[str, float]] = {}
    for i, lab in enumerate(TRAINING_LABELS):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(3) if r != i)
        fn = sum(cm[i][c] for c in range(3) if c != i)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        support = sum(cm[i])
        out[lab] = {
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "support": float(support),
        }
    return out


def macro_f1(prf: dict[str, dict[str, float]]) -> float:
    vals = [prf[lab]["f1"] for lab in TRAINING_LABELS]
    return float(sum(vals) / len(vals))


def balanced_accuracy(predictions: Sequence[dict[str, Any]]) -> float:
    prf = per_class_prf(predictions)
    recalls = [prf[lab]["recall"] for lab in TRAINING_LABELS if prf[lab]["support"] > 0]
    return float(sum(recalls) / len(recalls)) if recalls else 0.0


def fold_support(predictions: Sequence[dict[str, Any]]) -> dict[str, int]:
    c = Counter(p["label"] for p in predictions if not p.get("synthetic"))
    return {lab: int(c.get(lab, 0)) for lab in TRAINING_LABELS}


def summarize_oof(predictions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    prf = per_class_prf(project)
    return {
        "kind": "source-group-isolated out-of-fold prototype diagnostics",
        "n_examples": len(project),
        "class_support": fold_support(project),
        "risk_head_metrics": risk_head_metrics(project),
        "public_routing_matrix": public_routing_matrix(project),
        "confusion_matrix_forced_argmax": confusion_matrix(project),
        "per_class_forced_argmax": prf,
        "macro_f1_forced_argmax": macro_f1(prf),
        "balanced_accuracy_forced_argmax": balanced_accuracy(project),
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
