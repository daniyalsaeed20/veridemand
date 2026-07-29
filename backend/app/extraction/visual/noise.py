"""Provisional OCR item noise classification (Phase 4).

Does not perform handwriting recognition or claim handwriting authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from backend.app.contracts.ocr import ProvisionalItemClass, ProvisionalItemCounts

_SYMBOL_RE = re.compile(r"^[\W_]+$", re.UNICODE)
_NUMERIC_RE = re.compile(r"^\d{1,3}$")


@dataclass(frozen=True, slots=True)
class ClassifiedItem:
    index: int
    text: str
    provisional_class: ProvisionalItemClass
    publish_in_transcript: bool


def _box_aspect(poly: list[tuple[float, float]]) -> tuple[float, float, float]:
    if not poly:
        return 0.0, 0.0, 1.0
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    w = max(1e-6, max(xs) - min(xs))
    h = max(1e-6, max(ys) - min(ys))
    return w, h, max(w / h, h / w)


def classify_raw_item(
    raw: Any,
    *,
    low_confidence_threshold: float,
    is_line_only_artefact: bool = False,
    page_has_dense_form: bool = False,
) -> ClassifiedItem:
    """Classify one raw OCR line (or word-like item) without final HTR claims."""

    text = str(getattr(raw, "text", "") or "").strip()
    score = float(getattr(raw, "recognition_score", getattr(raw, "score", 0.0)) or 0.0)
    poly = getattr(raw, "polygon_px", None) or []
    _w, _h, aspect = _box_aspect(poly)
    idx = int(getattr(raw, "sequence_index", 0) or 0)

    if is_line_only_artefact:
        return ClassifiedItem(
            index=idx,
            text=text,
            provisional_class=ProvisionalItemClass.LINE_OR_GRID_ARTEFACT,
            publish_in_transcript=False,
        )

    if not text:
        return ClassifiedItem(
            index=idx,
            text=text,
            provisional_class=ProvisionalItemClass.UNRESOLVED,
            publish_in_transcript=False,
        )

    if _SYMBOL_RE.match(text) and len(text) <= 3:
        return ClassifiedItem(
            index=idx,
            text=text,
            provisional_class=ProvisionalItemClass.CHECKBOX_OR_SYMBOL_CANDIDATE,
            publish_in_transcript=False,
        )

    if page_has_dense_form and _NUMERIC_RE.match(text) and aspect < 2.5 and len(text) <= 3:
        # Isolated form-field numbers — keep geometry but separate from reading text.
        return ClassifiedItem(
            index=idx,
            text=text,
            provisional_class=ProvisionalItemClass.ISOLATED_FORM_NUMBER,
            publish_in_transcript=False,
        )

    # Irregular aspect + low confidence → handwriting candidate pending Phase 5.
    if score < 0.45 and aspect < 1.35 and len(text) >= 2 and not text.isupper():
        return ClassifiedItem(
            index=idx,
            text=text,
            provisional_class=ProvisionalItemClass.HANDWRITING_CANDIDATE_PENDING_PHASE_5,
            publish_in_transcript=False,
        )

    if score < low_confidence_threshold:
        return ClassifiedItem(
            index=idx,
            text=text,
            provisional_class=ProvisionalItemClass.LOW_CONFIDENCE_TEXT,
            publish_in_transcript=True,
        )

    if len(text) == 1 and text.isalnum() and page_has_dense_form and score < 0.9:
        return ClassifiedItem(
            index=idx,
            text=text,
            provisional_class=ProvisionalItemClass.UNRESOLVED,
            publish_in_transcript=False,
        )

    return ClassifiedItem(
        index=idx,
        text=text,
        provisional_class=ProvisionalItemClass.CREDIBLE_PRINTED_TEXT,
        publish_in_transcript=True,
    )


def classify_raw_lines(
    raw_lines: list[Any],
    *,
    low_confidence_threshold: float,
    line_only_indices: set[int] | frozenset[int],
    page_has_dense_form: bool,
) -> list[ClassifiedItem]:
    results: list[ClassifiedItem] = []
    for idx, line in enumerate(raw_lines):
        item = classify_raw_item(
            line,
            low_confidence_threshold=low_confidence_threshold,
            is_line_only_artefact=idx in line_only_indices,
            page_has_dense_form=page_has_dense_form,
        )
        results.append(
            ClassifiedItem(
                index=idx,
                text=item.text,
                provisional_class=item.provisional_class,
                publish_in_transcript=item.publish_in_transcript,
            )
        )
    return results


def count_provisional_classes(items: list[ClassifiedItem]) -> ProvisionalItemCounts:
    counts = ProvisionalItemCounts()
    for item in items:
        cls = item.provisional_class
        if cls is ProvisionalItemClass.CREDIBLE_PRINTED_TEXT:
            counts = counts.model_copy(update={"credible_text": counts.credible_text + 1})
        elif cls is ProvisionalItemClass.LOW_CONFIDENCE_TEXT:
            counts = counts.model_copy(update={"low_confidence": counts.low_confidence + 1})
        elif cls is ProvisionalItemClass.ISOLATED_FORM_NUMBER:
            counts = counts.model_copy(
                update={"isolated_form_numbers": counts.isolated_form_numbers + 1}
            )
        elif cls is ProvisionalItemClass.CHECKBOX_OR_SYMBOL_CANDIDATE:
            counts = counts.model_copy(update={"symbol_candidates": counts.symbol_candidates + 1})
        elif cls is ProvisionalItemClass.LINE_OR_GRID_ARTEFACT:
            counts = counts.model_copy(update={"artefacts": counts.artefacts + 1})
        elif cls is ProvisionalItemClass.HANDWRITING_CANDIDATE_PENDING_PHASE_5:
            counts = counts.model_copy(
                update={"handwriting_pending": counts.handwriting_pending + 1}
            )
        else:
            counts = counts.model_copy(update={"unresolved": counts.unresolved + 1})
    return counts
