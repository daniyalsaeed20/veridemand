"""Deterministic SourceSpan construction from native SourceTokens."""

from __future__ import annotations

from app.models.enums import ExtractionMethod
from app.models.source_span import SourceSpan
from app.models.source_token import SourceToken
from app.services.session.workspace import new_opaque_id


def group_tokens_into_spans(
    tokens: list[SourceToken],
    *,
    line_y_tolerance: float = 0.015,
    max_x_gap: float = 0.08,
    max_column_x_gap: float = 0.25,
) -> list[SourceSpan]:
    """Group tokens into readable line spans without merging distant columns.

    Tokens are assumed roughly reading-ordered. A new span starts when the next
    token jumps to a new line or leaves a large horizontal gap (column break).
    """
    if not tokens:
        return []

    spans: list[SourceSpan] = []
    current: list[SourceToken] = [tokens[0]]

    for token in tokens[1:]:
        prev = current[-1]
        prev_box = _bbox(prev.polygon)
        cur_box = _bbox(token.polygon)
        same_line = abs(prev_box[1] - cur_box[1]) <= line_y_tolerance
        x_gap = cur_box[0] - prev_box[2]
        if same_line and 0 <= x_gap <= max_x_gap:
            current.append(token)
            continue
        if same_line and x_gap > max_column_x_gap:
            spans.append(_make_span(current))
            current = [token]
            continue
        if same_line and x_gap > max_x_gap:
            spans.append(_make_span(current))
            current = [token]
            continue
        # New line or upward jump
        spans.append(_make_span(current))
        current = [token]

    if current:
        spans.append(_make_span(current))
    return spans


def _bbox(polygon: list[list[float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _make_span(tokens: list[SourceToken]) -> SourceSpan:
    text = " ".join(t.text for t in tokens if t.text)
    polygons = [t.polygon for t in tokens]
    confidences = [t.confidence for t in tokens]
    confidence = sum(confidences) / len(confidences) if confidences else None
    return SourceSpan(
        id=new_opaque_id("span"),
        document_id=tokens[0].document_id,
        page_number=tokens[0].page_number,
        text=text,
        token_ids=[t.id for t in tokens],
        polygons=polygons,
        method=ExtractionMethod.NATIVE,
        confidence=confidence,
    )
