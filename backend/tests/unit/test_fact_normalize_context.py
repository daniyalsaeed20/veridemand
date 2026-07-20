"""Unit tests for Phase 5 normalizers, context, consolidate, status."""

from __future__ import annotations

from app.models.enums import ExtractionMethod, FactStatus
from app.models.source_span import SourceSpan
from app.services.facts.consolidate import consolidate_hits
from app.services.facts.context import build_lines, find_label_matches, is_footer_line
from app.services.facts.normalize import (
    normalize_candidate,
    normalize_cpt,
    normalize_currency,
    normalize_date,
    normalize_email,
    normalize_icd10,
    normalize_phone,
)
from app.services.facts.status import score_and_status
from app.services.facts.types import ParserHit


def _span(text: str, y0: float = 0.2, sid: str = "span_01TEST000000000000000001") -> SourceSpan:
    return SourceSpan(
        id=sid,
        document_id="doc_01TEST000000000000000001",
        page_number=1,
        text=text,
        token_ids=[],
        polygons=[[(0.1, y0), (0.5, y0), (0.5, y0 + 0.02), (0.1, y0 + 0.02)]],
        method=ExtractionMethod.NATIVE,
        confidence=0.95,
    )


def test_normalize_date_formats() -> None:
    assert normalize_date("2024-01-15")[0] == "2024-01-15"
    assert normalize_date("01/15/2024")[0] == "2024-01-15"
    assert normalize_date("January 15, 2024")[0] == "2024-01-15"
    assert normalize_date("not-a-date")[0] is None


def test_normalize_invalid_date_not_invented() -> None:
    assert normalize_date("02/30/2024")[0] is None


def test_normalize_currency_decimal_string() -> None:
    assert normalize_currency("$1,234.56")[0] == "1234.56"
    assert normalize_currency("(100.00)")[0] == "-100.00"
    assert normalize_currency("12.3O")[0] is None  # OCR confusion


def test_normalize_phone_email_codes() -> None:
    assert normalize_phone("(206) 555-1212")[0] == "+12065551212"
    assert normalize_email("User@Example.COM")[0] == "user@example.com"
    assert normalize_cpt("99213")[0] == "99213"
    assert normalize_cpt("123")[0] is None
    assert normalize_icd10("S13.4")[0] == "S13.4"
    assert normalize_icd10("ZZZ")[0] is None


def test_normalize_candidate_money_display() -> None:
    norm, display, warn = normalize_candidate("money", "$50.00")
    assert norm == "50.00"
    assert display == "$50.00"
    assert warn is None


def test_context_label_and_footer() -> None:
    spans = [
        _span("Date of Loss: 01/15/2024", 0.2, "span_01TEST000000000000000001"),
        _span("Printed on 03/01/2024", 0.92, "span_01TEST000000000000000002"),
    ]
    lines = build_lines(spans, 1)
    assert len(lines) == 2
    assert is_footer_line(lines[1])
    hits = find_label_matches(lines, ("Date of Loss",))
    assert len(hits) == 1


def test_consolidate_identical_values_merges_spans() -> None:
    h1 = ParserHit(
        fact_type="claim.number",
        raw_value="CLM-1",
        normalized_value="CLM-1",
        display_value="CLM-1",
        source_span_ids=("span_01TEST000000000000000001",),
        document_id="doc_01TEST000000000000000001",
        page_number=1,
        label_context="Claim Number",
        parser_id="det.claim.number.v1",
        extraction_methods=("context_parser",),
        confidence=0.9,
        criticality="critical",
    )
    h2 = ParserHit(
        fact_type="claim.number",
        raw_value="CLM-1",
        normalized_value="CLM-1",
        display_value="CLM-1",
        source_span_ids=("span_01TEST000000000000000002",),
        document_id="doc_01TEST000000000000000001",
        page_number=2,
        label_context="Claim Number",
        parser_id="det.claim.number.v1",
        extraction_methods=("context_parser",),
        confidence=0.85,
        criticality="critical",
    )
    merged = consolidate_hits([h1, h2])
    assert len(merged) == 1
    assert set(merged[0].source_span_ids) == {
        "span_01TEST000000000000000001",
        "span_01TEST000000000000000002",
    }


def test_consolidate_different_types_not_merged() -> None:
    h1 = ParserHit(
        fact_type="claim.number",
        raw_value="ABC",
        normalized_value="ABC",
        display_value="ABC",
        source_span_ids=("span_01TEST000000000000000001",),
        document_id="doc_01TEST000000000000000001",
        page_number=1,
        label_context="Claim",
        parser_id="det.claim.number.v1",
        extraction_methods=("context_parser",),
        confidence=0.9,
        criticality="critical",
    )
    h2 = ParserHit(
        fact_type="policy.number",
        raw_value="ABC",
        normalized_value="ABC",
        display_value="ABC",
        source_span_ids=("span_01TEST000000000000000002",),
        document_id="doc_01TEST000000000000000001",
        page_number=1,
        label_context="Policy",
        parser_id="det.policy.number.v1",
        extraction_methods=("context_parser",),
        confidence=0.9,
        criticality="critical",
    )
    assert len(consolidate_hits([h1, h2])) == 2


def test_status_secondary_never_verified() -> None:
    hit = ParserHit(
        fact_type="claim.number",
        raw_value="CLM-9",
        normalized_value="CLM-9",
        display_value="CLM-9",
        source_span_ids=("span_01TEST000000000000000001",),
        document_id="doc_01TEST000000000000000001",
        page_number=1,
        label_context="Claim Number",
        parser_id="det.claim.number.v1",
        extraction_methods=("context_parser",),
        confidence=0.99,
        criticality="critical",
        secondary_source=True,
    )
    _conf, status = score_and_status(hit)
    assert status == FactStatus.NEEDS_REVIEW


def test_status_ambiguous_classification_blocks_verify() -> None:
    hit = ParserHit(
        fact_type="damages.charge",
        raw_value="100.00",
        normalized_value="100.00",
        display_value="$100.00",
        source_span_ids=("span_01TEST000000000000000001",),
        document_id="doc_01TEST000000000000000001",
        page_number=1,
        label_context="Charge",
        parser_id="det.damages.charge.v1",
        extraction_methods=("context_parser",),
        confidence=0.99,
        criticality="normal",
        classification_ambiguous=True,
    )
    _conf, status = score_and_status(hit)
    assert status == FactStatus.NEEDS_REVIEW
