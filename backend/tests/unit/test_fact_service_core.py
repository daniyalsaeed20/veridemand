"""FactService conflict, gap, calculation, and zero-LLM unit tests."""

from __future__ import annotations

from pathlib import Path

from app.models.app_settings import AppSettings
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.enums import (
    ClassificationStatus,
    DocumentClassification,
    DocumentFileType,
    DocumentStatus,
    ExtractionMethod,
    FactStatus,
    PageRoute,
    SafetyArchetype,
)
from app.models.fact import Fact
from app.models.source_span import SourceSpan
from app.services.facts.calculations import count_visits, sum_money
from app.services.facts.conflicts import create_gap_reviews, detect_exact_conflicts
from app.services.facts.service import FactService
from app.services.session.service import SessionService


def test_detect_exact_conflicts_keeps_both() -> None:
    facts = [
        Fact(
            id="fact_01CONFLICTA0000000000001",
            session_id="ses_01CONFLICT0000000000001",
            fact_type="collision.date",
            raw_value="01/15/2024",
            normalized_value="2024-01-15",
            confidence=0.9,
            status=FactStatus.SUGGESTED,
            source_span_ids=["span_01A000000000000000000001"],
            extraction_methods=["context_parser"],
            criticality="critical",
        ),
        Fact(
            id="fact_01CONFLICTB0000000000001",
            session_id="ses_01CONFLICT0000000000001",
            fact_type="collision.date",
            raw_value="01/16/2024",
            normalized_value="2024-01-16",
            confidence=0.9,
            status=FactStatus.SUGGESTED,
            source_span_ids=["span_01B000000000000000000001"],
            extraction_methods=["context_parser"],
            criticality="critical",
        ),
    ]
    updated, issues = detect_exact_conflicts("ses_01CONFLICT0000000000001", facts)
    assert all(f.status == FactStatus.CONFLICTING for f in updated)
    assert len(issues) == 1
    assert issues[0].issue_type == "collision.date_of_loss_conflict"
    assert set(issues[0].fact_ids or []) == {
        "fact_01CONFLICTA0000000000001",
        "fact_01CONFLICTB0000000000001",
    }


def test_gap_reviews_no_placeholder_facts() -> None:
    issues = create_gap_reviews(
        "ses_01GAP00000000000000000001",
        [],
        inspected_document_ids=["doc_01GAP00000000000000000001"],
    )
    assert any(i.issue_type == "extraction.missing_critical_fact" for i in issues)
    assert any("client.name" in i.title for i in issues)


def test_calculations_decimal_safe() -> None:
    sid = "ses_01CALC0000000000000000001"
    charges = [
        Fact(
            id="fact_01CALCA0000000000000001",
            session_id=sid,
            fact_type="damages.charge",
            raw_value="10.10",
            normalized_value="10.10",
            confidence=1.0,
            status=FactStatus.SUGGESTED,
            source_span_ids=["span_01C000000000000000000001"],
            extraction_methods=["context_parser"],
        ),
        Fact(
            id="fact_01CALCB0000000000000001",
            session_id=sid,
            fact_type="damages.charge",
            raw_value="0.20",
            normalized_value="0.20",
            confidence=1.0,
            status=FactStatus.SUGGESTED,
            source_span_ids=["span_01C000000000000000000002"],
            extraction_methods=["context_parser"],
        ),
    ]
    summed = sum_money(sid, charges)
    assert len(summed) == 1
    assert summed[0].normalized_value == "10.30"
    assert summed[0].provenance == "calculated"

    visits = [
        Fact(
            id="fact_01CALCV0000000000000001",
            session_id=sid,
            fact_type="medical.visit_date",
            raw_value="2024-01-01",
            normalized_value="2024-01-01",
            confidence=1.0,
            status=FactStatus.SUGGESTED,
            source_span_ids=["span_01V000000000000000000001"],
            extraction_methods=["context_parser"],
        ),
        Fact(
            id="fact_01CALCV0000000000000002",
            session_id=sid,
            fact_type="medical.visit_date",
            raw_value="2024-01-01",
            normalized_value="2024-01-01",
            confidence=1.0,
            status=FactStatus.SUGGESTED,
            source_span_ids=["span_01V000000000000000000002"],
            extraction_methods=["context_parser"],
        ),
    ]
    counted = count_visits(sid, visits)
    assert counted[0].normalized_value == 1


def test_fact_service_zero_llm_and_authority(tmp_path: Path) -> None:
    settings = AppSettings(enable_llm_semantic_extraction=True)
    sessions = SessionService(app_settings=settings, temp_root=tmp_path / "s")
    facts = FactService(session_service=sessions, app_settings=settings)
    session = sessions.create_session()

    demand = Document(
        id="doc_01DEMAND0000000000000001",
        session_id=session.id,
        display_name="demand.pdf",
        file_type=DocumentFileType.PDF,
        content_sha256="b" * 64,
        status=DocumentStatus.CLASSIFIED,
        classification=DocumentClassification.EXISTING_DEMAND,
        safety_archetype=SafetyArchetype.EXISTING_DEMAND,
        exclude_from_drafting=True,
        treat_as_secondary_evidence=False,
        classification_status=ClassificationStatus.USER_CONFIRMED,
    )
    police = Document(
        id="doc_01POLICE0000000000000001",
        session_id=session.id,
        display_name="police.pdf",
        file_type=DocumentFileType.PDF,
        content_sha256="c" * 64,
        status=DocumentStatus.CLASSIFIED,
        classification=DocumentClassification.POLICE_REPORT,
        classification_status=ClassificationStatus.USER_CONFIRMED,
        exclude_from_drafting=False,
    )
    record = sessions.get_record(session.id)
    record.documents[demand.id] = demand
    record.documents[police.id] = police
    record.pages[police.id] = [
        DocumentPage(
            id="pg1",
            document_id=police.id,
            page_number=1,
            width=200,
            height=200,
            route=PageRoute.NATIVE,
            extraction_method=ExtractionMethod.NATIVE,
        )
    ]
    record.spans_by_page[police.id] = {
        1: [
            SourceSpan(
                id="span_01POLICE0000000000000001",
                document_id=police.id,
                page_number=1,
                text="Date of Loss: 03/10/2023",
                token_ids=[],
                polygons=[[(0.1, 0.2), (0.8, 0.2), (0.8, 0.25), (0.1, 0.25)]],
                method=ExtractionMethod.NATIVE,
                confidence=0.97,
            ),
            SourceSpan(
                id="span_01POLICE0000000000000002",
                document_id=police.id,
                page_number=1,
                text="Claim Number: CLM-555",
                token_ids=[],
                polygons=[[(0.1, 0.3), (0.8, 0.3), (0.8, 0.35), (0.1, 0.35)]],
                method=ExtractionMethod.NATIVE,
                confidence=0.97,
            ),
        ]
    }
    # Demand has tempting spans but must be suppressed
    record.pages[demand.id] = [
        DocumentPage(
            id="pgd",
            document_id=demand.id,
            page_number=1,
            width=200,
            height=200,
            route=PageRoute.NATIVE,
            extraction_method=ExtractionMethod.NATIVE,
        )
    ]
    record.spans_by_page[demand.id] = {
        1: [
            SourceSpan(
                id="span_01DEMAND0000000000000001",
                document_id=demand.id,
                page_number=1,
                text="Claim Number: FAKE-999",
                token_ids=[],
                polygons=[[(0.1, 0.2), (0.8, 0.2), (0.8, 0.25), (0.1, 0.25)]],
                method=ExtractionMethod.NATIVE,
                confidence=0.99,
            )
        ]
    }

    result = facts.extract_session_facts(session.id, record.generation)
    assert result.llm_calls == 0
    assert facts.llm_call_count == 0
    claim_vals = [
        f.normalized_value
        for f in result.facts
        if f.fact_type == "claim.number" and f.provenance == "deterministic"
    ]
    assert "CLM-555" in claim_vals
    assert "FAKE-999" not in claim_vals
    assert result.documents_suppressed_authority >= 1
