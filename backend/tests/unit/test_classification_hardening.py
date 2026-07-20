"""Phase 4 hardening: Stage A safety + high-score conflict review."""

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
from app.models.geometry import NormalizedPolygon
from app.models.source_span import SourceSpan
from app.services.classification.archetype import assess_safety_archetype
from app.services.classification.authority import (
    apply_authority_policy,
    enforce_authority_invariant,
    is_authoritative_evidence,
    is_primary_authoritative,
)
from app.services.classification.decision import select_rule_decision
from app.services.classification.features import build_classification_features
from app.services.classification.rules import score_rules


def _doc(
    name: str,
    *,
    file_type: DocumentFileType = DocumentFileType.PDF,
    page_count: int = 1,
) -> Document:
    return Document(
        id="doc_hard000000000000000001",
        session_id="ses_test00000000000000001",
        display_name=name,
        file_type=file_type,
        content_sha256="e" * 64,
        status=DocumentStatus.EXTRACTED,
        page_count=page_count,
    )


def _classify(name: str, text: str, *, file_type: DocumentFileType = DocumentFileType.PDF):
    doc = _doc(name, file_type=file_type, page_count=5 if file_type == DocumentFileType.DOCX else 1)
    page = DocumentPage(
        id="page_hard00000000000000001",
        document_id=doc.id,
        page_number=1,
        width=200,
        height=200,
        route=PageRoute.NATIVE,
        extraction_method=ExtractionMethod.NATIVE,
        token_count=max(1, len(text.split())),
    )
    poly: NormalizedPolygon = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.2], [0.1, 0.2]]
    span = SourceSpan(
        id="span_hard0000000000000001",
        document_id=doc.id,
        page_number=1,
        text=text,
        token_ids=[],
        polygons=[poly],
        method=ExtractionMethod.NATIVE,
        confidence=0.95,
    )
    features = build_classification_features(doc, pages=[page], spans_by_page={1: [span]})
    arch = assess_safety_archetype(features)
    scores = score_rules(features)
    decision = select_rule_decision(features, scores, threshold=0.55, archetype=arch)
    assert decision is not None
    return features, arch, decision


def test_demand_with_police_section_is_existing_demand_and_restricted() -> None:
    _, arch, decision = _classify(
        "package.pdf",
        "Demand for Settlement RE: Your Insured Very Truly Yours "
        "Police Report Collision Report General Damages",
    )
    assert arch.archetype == SafetyArchetype.EXISTING_DEMAND
    assert decision.classification == DocumentClassification.EXISTING_DEMAND
    assert decision.confidence >= 0.55
    assert decision.ambiguous or decision.needs_correction
    assert decision.classification_status in {
        ClassificationStatus.AMBIGUOUS,
        ClassificationStatus.NEEDS_CONFIRMATION,
    }
    doc = _doc("package.pdf")
    doc.classification = decision.classification
    doc.classification_confidence = decision.confidence
    apply_authority_policy(doc, archetype=arch.archetype)
    assert doc.exclude_from_drafting is True
    assert is_primary_authoritative(doc) is False


def test_high_police_score_cannot_override_demand_archetype() -> None:
    _, arch, decision = _classify(
        "letter.pdf",
        "Demand for Settlement RE: Your Insured Medical Specials Very Truly Yours "
        "Washington State Patrol Traffic Collision Report Reporting Officer",
    )
    assert arch.archetype == SafetyArchetype.EXISTING_DEMAND
    assert decision.classification == DocumentClassification.EXISTING_DEMAND
    assert "archetype_vs_category" in decision.conflicts or decision.ambiguous


def test_high_medical_score_cannot_override_demand_archetype() -> None:
    _, arch, decision = _classify(
        "letter.pdf",
        "Demand for Settlement RE: Your Insured General Damages Very Truly Yours "
        "Patient Information Medical Records Chief Complaint Physical Examination",
    )
    assert decision.classification == DocumentClassification.EXISTING_DEMAND
    assert arch.archetype == SafetyArchetype.EXISTING_DEMAND
    doc = _doc("letter.pdf")
    doc.classification = DocumentClassification.MEDICAL_RECORD  # simulate wrong label
    doc.safety_archetype = SafetyArchetype.EXISTING_DEMAND
    apply_authority_policy(doc, archetype=SafetyArchetype.EXISTING_DEMAND)
    enforce_authority_invariant(doc)
    assert is_primary_authoritative(doc) is False
    assert is_authoritative_evidence(doc) is False


def test_high_bill_score_cannot_override_demand_archetype() -> None:
    _, arch, decision = _classify(
        "letter.pdf",
        "Demand for Settlement RE: Your Insured Settlement Proposal Very Truly Yours "
        "Billing Ledger CPT Code Total Charges ICD-10",
    )
    assert decision.classification == DocumentClassification.EXISTING_DEMAND
    assert arch.archetype == SafetyArchetype.EXISTING_DEMAND


def test_score_above_threshold_still_ambiguous_with_conflict() -> None:
    _, _, decision = _classify(
        "letter.pdf",
        "Demand for Settlement RE: Your Insured Very Truly Yours Police Report",
    )
    assert decision.confidence >= 0.55
    assert decision.ambiguous is True
    assert decision.classification_status == ClassificationStatus.AMBIGUOUS


def test_police_mentioning_settlement_stays_police() -> None:
    _, arch, decision = _classify(
        "collision.pdf",
        "Washington State Patrol Traffic Collision Report Reporting Officer "
        "Driver mentioned a settlement demand from another party",
    )
    assert arch.archetype == SafetyArchetype.NONE
    assert decision.classification == DocumentClassification.POLICE_REPORT
    assert is_primary_authoritative(
        Document(
            id="doc_hard000000000000000002",
            session_id="ses_test00000000000000001",
            display_name="collision.pdf",
            file_type=DocumentFileType.PDF,
            content_sha256="f" * 64,
            status=DocumentStatus.CLASSIFIED,
            classification=decision.classification,
            safety_archetype=SafetyArchetype.NONE,
        )
    )


def test_docx_multi_evidence_summary_not_primary() -> None:
    _, arch, decision = _classify(
        "draft.docx",
        "Physical Examination ICD-10 Police Report Claim Number Medical Records Treatment Summary",
        file_type=DocumentFileType.DOCX,
    )
    assert arch.archetype in {
        SafetyArchetype.EXISTING_DEMAND,
        SafetyArchetype.UNCERTAIN_DERIVATIVE,
    }
    doc = _doc("draft.docx", file_type=DocumentFileType.DOCX, page_count=5)
    doc.classification = decision.classification
    apply_authority_policy(doc, archetype=arch.archetype)
    assert is_primary_authoritative(doc) is False


def test_template_placeholders_restricted() -> None:
    _, arch, decision = _classify(
        "firm-template.pdf",
        "Demand Template [CLIENT NAME] [INSERT claim number] firm template instructions",
    )
    assert arch.archetype == SafetyArchetype.TEMPLATE
    assert decision.classification == DocumentClassification.TEMPLATE
    doc = _doc("firm-template.pdf")
    apply_authority_policy(doc, archetype=arch.archetype)
    doc.classification = DocumentClassification.TEMPLATE
    assert is_primary_authoritative(doc) is False


def test_invariant_blocks_safety_plus_primary() -> None:
    doc = _doc("x.pdf")
    doc.classification = DocumentClassification.POLICE_REPORT
    doc.safety_archetype = SafetyArchetype.EXISTING_DEMAND
    doc.exclude_from_drafting = False
    enforce_authority_invariant(doc)
    assert doc.exclude_from_drafting is True
    assert is_primary_authoritative(doc) is False


def test_demand_without_demand_heading() -> None:
    _, arch, decision = _classify(
        "letter.pdf",
        "RE: Your Insured Settlement Proposal Policy Limits Demand "
        "General Damages Very Truly Yours Esq.",
    )
    assert arch.archetype == SafetyArchetype.EXISTING_DEMAND
    assert decision.classification == DocumentClassification.EXISTING_DEMAND
