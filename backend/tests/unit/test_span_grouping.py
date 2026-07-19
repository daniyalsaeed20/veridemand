"""Unit tests for deterministic span grouping."""

from __future__ import annotations

from app.models.enums import ExtractionMethod
from app.models.source_token import SourceToken
from app.services.extraction.spans import group_tokens_into_spans


def _tok(
    text: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    *,
    tok_id: str,
) -> SourceToken:
    return SourceToken(
        id=tok_id,
        document_id="doc_test000000000000000001",
        page_number=1,
        text=text,
        confidence=1.0,
        polygon=[[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        method=ExtractionMethod.NATIVE,
    )


def test_same_line_tokens_merge() -> None:
    tokens = [
        _tok("Hello", 0.10, 0.10, 0.18, 0.12, tok_id="tok_a"),
        _tok("world", 0.20, 0.10, 0.28, 0.12, tok_id="tok_b"),
    ]
    spans = group_tokens_into_spans(tokens)
    assert len(spans) == 1
    assert spans[0].text == "Hello world"
    assert spans[0].token_ids == ["tok_a", "tok_b"]


def test_distant_columns_do_not_merge() -> None:
    tokens = [
        _tok("Left", 0.05, 0.10, 0.15, 0.12, tok_id="tok_l"),
        _tok("Right", 0.70, 0.10, 0.85, 0.12, tok_id="tok_r"),
    ]
    spans = group_tokens_into_spans(tokens)
    assert len(spans) == 2
    assert spans[0].text == "Left"
    assert spans[1].text == "Right"
