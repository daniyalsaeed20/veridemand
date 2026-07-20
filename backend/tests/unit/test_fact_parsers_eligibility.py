"""Parser and eligibility unit tests for Phase 5."""

from __future__ import annotations

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.enums import (
    ClassificationStatus,
    DocumentClassification,
    DocumentFileType,
    DocumentStatus,
    ExtractionMethod,
    PageRoute,
    SafetyArchetype,
)
from app.models.source_span import SourceSpan
from app.services.facts.eligibility import document_eligibility, filter_usable_spans
from app.services.facts.parsers import parse_document_spans


def _doc(
    *,
    cls: DocumentClassification = DocumentClassification.POLICE_REPORT,
    status: DocumentStatus = DocumentStatus.CLASSIFIED,
    exclude: bool = False,
    secondary: bool = False,
    archetype: SafetyArchetype | None = None,
    class_status: ClassificationStatus | None = ClassificationStatus.USER_CONFIRMED,
) -> Document:
    return Document(
        id="doc_01FACTDOC000000000000001",
        session_id="ses_01FACTSES00000000000001",
        display_name="evidence.pdf",
        file_type=DocumentFileType.PDF,
        content_sha256="a" * 64,
        status=status,
        classification=cls,
        classification_status=class_status,
        safety_archetype=archetype,
        exclude_from_drafting=exclude,
        treat_as_secondary_evidence=secondary,
    )


def _span(text: str, y: float, n: int) -> SourceSpan:
    sid = f"span_01FACTSPAN{n:016d}"
    return SourceSpan(
        id=sid,
        document_id="doc_01FACTDOC000000000000001",
        page_number=1,
        text=text,
        token_ids=[],
        polygons=[[(0.05, y), (0.9, y), (0.9, y + 0.03), (0.05, y + 0.03)]],
        method=ExtractionMethod.NATIVE,
        confidence=0.96,
    )


def test_parse_date_of_loss_vs_visit_date() -> None:
    doc = _doc()
    spans = [
        _span("Date of Loss: 01/15/2024", 0.2, 1),
        _span("Date of Service: 02/01/2024", 0.35, 2),
    ]
    pages = [
        DocumentPage(
            id="page_1",
            document_id=doc.id,
            page_number=1,
            width=200,
            height=200,
            route=PageRoute.NATIVE,
            extraction_method=ExtractionMethod.NATIVE,
            ocr_status="not_needed",
        )
    ]
    # Police parsers include collision.date; medical visit needs medical class
    hits = parse_document_spans(
        doc, pages, {1: spans}, secondary=False, classification_ambiguous=False
    )
    types = {h.fact_type for h in hits}
    assert "collision.date" in types
    dol = next(h for h in hits if h.fact_type == "collision.date")
    assert dol.normalized_value == "2024-01-15"
    assert dol.source_span_ids


def test_claim_vs_policy_labels() -> None:
    doc = _doc(cls=DocumentClassification.INSURER_CORRESPONDENCE)
    spans = [
        _span("Claim Number: CLM-7788", 0.2, 1),
        _span("Policy Number: POL-9988", 0.3, 2),
    ]
    pages = [
        DocumentPage(
            id="page_1",
            document_id=doc.id,
            page_number=1,
            width=200,
            height=200,
            route=PageRoute.NATIVE,
            extraction_method=ExtractionMethod.NATIVE,
        )
    ]
    hits = parse_document_spans(
        doc, pages, {1: spans}, secondary=False, classification_ambiguous=False
    )
    by_type = {h.fact_type: h.normalized_value for h in hits}
    assert by_type.get("claim.number") == "CLM-7788"
    assert by_type.get("policy.number") == "POL-9988"


def test_icd10_rejects_arbitrary_alnum() -> None:
    doc = _doc(cls=DocumentClassification.MEDICAL_RECORD)
    spans = [_span("Diagnosis: ROOM12", 0.2, 1)]
    pages = [
        DocumentPage(
            id="page_1",
            document_id=doc.id,
            page_number=1,
            width=200,
            height=200,
            route=PageRoute.NATIVE,
            extraction_method=ExtractionMethod.NATIVE,
        )
    ]
    hits = parse_document_spans(
        doc, pages, {1: spans}, secondary=False, classification_ambiguous=False
    )
    assert not any(h.fact_type == "medical.diagnosis" for h in hits)


def test_template_and_excluded_not_eligible() -> None:
    tmpl = _doc(cls=DocumentClassification.TEMPLATE, exclude=True)
    assert document_eligibility(tmpl).eligible is False
    demand = _doc(
        cls=DocumentClassification.EXISTING_DEMAND,
        exclude=True,
        archetype=SafetyArchetype.EXISTING_DEMAND,
    )
    assert document_eligibility(demand).eligible is False
    demand.treat_as_secondary_evidence = True
    elig = document_eligibility(demand)
    assert elig.eligible is True
    assert elig.secondary is True


def test_primary_police_eligible() -> None:
    elig = document_eligibility(_doc())
    assert elig.eligible is True
    assert elig.secondary is False


def test_insufficient_coverage_page_suppressed() -> None:
    page = DocumentPage(
        id="page_1",
        document_id="doc_01FACTDOC000000000000001",
        page_number=1,
        width=200,
        height=200,
        route=PageRoute.OCR,
        quality_flags=["insufficient_coverage"],
        ocr_status="failed",
        extraction_method=ExtractionMethod.OCR,
    )
    spans = [_span("Claim Number: X", 0.2, 1)]
    usable, suppressed, count = filter_usable_spans([page], {1: spans})
    assert suppressed == 1
    assert usable == {}
    assert count == 0


def test_ambiguous_primary_flags_classification() -> None:
    doc = _doc(
        cls=DocumentClassification.BILL_LEDGER,
        class_status=ClassificationStatus.AMBIGUOUS,
    )
    elig = document_eligibility(doc)
    assert elig.eligible is True
    assert elig.classification_ambiguous is True
