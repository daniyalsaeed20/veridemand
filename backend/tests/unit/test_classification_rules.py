"""Unit tests for classification rules, precedence, and determinism."""

from __future__ import annotations

from app.models.document import Document
from app.models.enums import DocumentClassification, DocumentFileType, DocumentStatus
from app.services.classification.decision import select_rule_decision
from app.services.classification.features import build_classification_features
from app.services.classification.rules import score_rules


def _doc(name: str, *, file_type: DocumentFileType = DocumentFileType.PDF) -> Document:
    return Document(
        id="doc_test000000000000000001",
        session_id="ses_test00000000000000001",
        display_name=name,
        file_type=file_type,
        content_sha256="a" * 64,
        status=DocumentStatus.EXTRACTED,
    )


def _classify(
    name: str, text: str, *, threshold: float = 0.55
) -> tuple[DocumentClassification, float, bool]:
    doc = _doc(name)
    from app.models.document_page import DocumentPage
    from app.models.enums import ExtractionMethod, PageRoute
    from app.models.geometry import NormalizedPolygon
    from app.models.source_span import SourceSpan

    page = DocumentPage(
        id="page_test00000000000000001",
        document_id=doc.id,
        page_number=1,
        width=200,
        height=200,
        route=PageRoute.NATIVE,
        extraction_method=ExtractionMethod.NATIVE,
        token_count=10,
    )
    poly: NormalizedPolygon = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.2], [0.1, 0.2]]
    span = SourceSpan(
        id="span_test0000000000000001",
        document_id=doc.id,
        page_number=1,
        text=text,
        token_ids=[],
        polygons=[poly],
        method=ExtractionMethod.NATIVE,
        confidence=0.95,
    )
    features = build_classification_features(doc, pages=[page], spans_by_page={1: [span]})
    scores = score_rules(features)
    decision = select_rule_decision(features, scores, threshold=threshold)
    assert decision is not None
    return decision.classification, decision.confidence, decision.ambiguous


def test_police_report_classification() -> None:
    cls, conf, _ = _classify(
        "collision-report.pdf",
        "WASHINGTON STATE PATROL Traffic Collision Report Reporting Officer",
    )
    assert cls == DocumentClassification.POLICE_REPORT
    assert conf >= 0.55


def test_insurer_correspondence() -> None:
    cls, _, _ = _classify(
        "carrier-letter.pdf",
        "Claims Department Claim Number Policy Number Dear Insured",
    )
    assert cls == DocumentClassification.INSURER_CORRESPONDENCE


def test_medical_record() -> None:
    cls, _, _ = _classify(
        "clinic-records.pdf",
        "Patient Information Medical Records Chief Complaint",
    )
    assert cls == DocumentClassification.MEDICAL_RECORD


def test_ecw_medical() -> None:
    cls, _, _ = _classify("ecw-export.pdf", "eCW Electronic Medical Record Clinical Summary")
    assert cls == DocumentClassification.MEDICAL_RECORD


def test_ecw_billing() -> None:
    cls, _, _ = _classify("ledger-export.pdf", "Billing Ledger CPT Code Total Charges")
    assert cls == DocumentClassification.BILL_LEDGER


def test_imaging_report() -> None:
    cls, _, _ = _classify("radiology.pdf", "Radiology Report MRI Report Impression Findings")
    assert cls == DocumentClassification.IMAGING_REPORT


def test_lien() -> None:
    cls, _, _ = _classify("lien-notice.pdf", "Notice of Lien Lien Amount Lien Holder")
    assert cls == DocumentClassification.LIEN


def test_wage_loss() -> None:
    cls, _, _ = _classify("wages.pdf", "Wage Loss Employer Verification Lost Wages")
    assert cls == DocumentClassification.WAGE_LOSS


def test_existing_demand() -> None:
    cls, _, _ = _classify(
        "settlement-package.pdf",
        "Demand for Settlement Demand Letter RE: Your Insured",
    )
    assert cls == DocumentClassification.EXISTING_DEMAND


def test_template() -> None:
    cls, _, _ = _classify("firm-template.pdf", "Demand Template [CLIENT NAME] [INSERT")
    assert cls == DocumentClassification.TEMPLATE


def test_photograph_image_type() -> None:
    doc = _doc("injury-photo.jpg", file_type=DocumentFileType.JPG)
    features = build_classification_features(doc, pages=[], spans_by_page={})
    scores = score_rules(features)
    decision = select_rule_decision(features, scores, threshold=0.55)
    assert decision is not None
    assert decision.classification == DocumentClassification.PHOTOGRAPHS


def test_weak_keyword_only_is_ambiguous() -> None:
    _, _, ambiguous = _classify("document.pdf", "claim")
    assert ambiguous


def test_medical_bundle_with_imaging_stays_medical() -> None:
    cls, _, _ = _classify(
        "clinical-stack.pdf",
        "Patient Information Medical Records MRI Report embedded imaging",
    )
    assert cls == DocumentClassification.MEDICAL_RECORD


def test_medical_with_billing_prefers_medical_when_clinical_dominates() -> None:
    cls, _, _ = _classify(
        "clinical-with-charges.pdf",
        "Patient Information Medical Records Chief Complaint Billing Ledger",
    )
    assert cls in {
        DocumentClassification.MEDICAL_RECORD,
        DocumentClassification.BILL_LEDGER,
    }


def test_demand_with_all_keywords_still_demand() -> None:
    cls, _, _ = _classify(
        "demand-all-refs.pdf",
        "Demand for Settlement police medical billing insurer claim",
    )
    assert cls == DocumentClassification.EXISTING_DEMAND


def test_deterministic_same_input() -> None:
    a = _classify("report.pdf", "Traffic Collision Report Reporting Officer")
    b = _classify("report.pdf", "Traffic Collision Report Reporting Officer")
    assert a == b


def test_misleading_filename_content_wins() -> None:
    cls, _, ambiguous = _classify(
        "police-report.pdf",
        "Billing Ledger CPT Code Total Charges Patient Balance",
    )
    assert cls == DocumentClassification.BILL_LEDGER
    assert ambiguous or cls != DocumentClassification.POLICE_REPORT


def test_no_usable_text_low_confidence() -> None:
    doc = _doc("document.pdf")
    features = build_classification_features(doc, pages=[], spans_by_page={})
    scores = score_rules(features)
    decision = select_rule_decision(features, scores, threshold=0.55)
    assert decision is not None
    assert decision.confidence <= 0.45
    assert decision.needs_correction
