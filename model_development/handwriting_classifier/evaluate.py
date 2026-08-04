"""Aggregate OOF metrics and confusion matrices (privacy-safe)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

import numpy as np

from model_development.handwriting_classifier.config import CLASS_ORDER


def confusion_matrix(
    predictions: Sequence[dict[str, Any]],
    *,
    use_argmax: bool = True,
) -> dict[str, Any]:
    labels = list(CLASS_ORDER)
    index = {lab: i for i, lab in enumerate(labels)}
    mat = np.zeros((3, 3), dtype=np.int64)
    for p in predictions:
        if p.get("synthetic"):
            continue
        true = p["label"]
        if true not in index:
            continue
        if use_argmax:
            pred = CLASS_ORDER[int(np.argmax(p["probabilities"]))]
        else:
            pred = p.get("routed_outcome", CLASS_ORDER[int(np.argmax(p["probabilities"]))])
        if pred not in index:
            continue
        mat[index[true], index[pred]] += 1
    return {
        "labels": labels,
        "matrix": mat.tolist(),
    }


def per_class_prf(predictions: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    cm = confusion_matrix(predictions)["matrix"]
    out: dict[str, dict[str, float]] = {}
    for i, lab in enumerate(CLASS_ORDER):
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
    vals = [prf[lab]["f1"] for lab in CLASS_ORDER]
    return float(sum(vals) / len(vals))


def balanced_accuracy(predictions: Sequence[dict[str, Any]]) -> float:
    prf = per_class_prf(predictions)
    recalls = [prf[lab]["recall"] for lab in CLASS_ORDER if prf[lab]["support"] > 0]
    return float(sum(recalls) / len(recalls)) if recalls else 0.0


def fold_support(predictions: Sequence[dict[str, Any]]) -> dict[str, int]:
    c = Counter(p["label"] for p in predictions if not p.get("synthetic"))
    return {lab: int(c.get(lab, 0)) for lab in CLASS_ORDER}


def summarize_oof(predictions: Sequence[dict[str, Any]]) -> dict[str, Any]:
    project = [p for p in predictions if not p.get("synthetic") and not p.get("public")]
    prf = per_class_prf(project)
    return {
        "kind": "source-group-isolated out-of-fold prototype diagnostics",
        "n_examples": len(project),
        "class_support": fold_support(project),
        "confusion_matrix": confusion_matrix(project),
        "per_class": prf,
        "macro_f1": macro_f1(prf),
        "balanced_accuracy": balanced_accuracy(project),
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
            outcome = CLASS_ORDER[int(np.argmax(p["probabilities"]))]
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
            if "signature" in cats_src and outcome != "handwritten":
                cats["signatures_confused"] += 1
            if "digits" in cats_src and outcome != "handwritten":
                cats["handwritten_digits_confused"] += 1
            if "cursive" in cats_src and outcome != "handwritten":
                cats["cursive_confused"] += 1
        w = int(p.get("width") or 0)
        h = int(p.get("height") or 0)
        if w and h and w * h < 40 * 40 and outcome != true:
            cats["small_crops_confused"] += 1
        if w and h and max(w, h) / max(min(w, h), 1) > 8 and outcome != true:
            cats["broad_crops_confused"] += 1
    return dict(cats)
