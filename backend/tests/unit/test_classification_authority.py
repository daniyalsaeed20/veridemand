"""FR-CLS-06 authority guard tests."""

from __future__ import annotations

from app.core.domain_errors import DomainError
from app.models.document import Document
from app.models.enums import DocumentClassification, DocumentFileType, DocumentStatus
from app.services.classification.authority import (
    apply_authority_defaults,
    is_authoritative_evidence,
    validate_authority_patch,
)


def _doc(cls: DocumentClassification) -> Document:
    return Document(
        id="doc_auth000000000000000001",
        session_id="ses_test00000000000000001",
        display_name="file.pdf",
        file_type=DocumentFileType.PDF,
        content_sha256="d" * 64,
        status=DocumentStatus.CLASSIFIED,
        classification=cls,
    )


def test_existing_demand_excluded_by_default() -> None:
    doc = _doc(DocumentClassification.EXISTING_DEMAND)
    apply_authority_defaults(doc)
    assert doc.treat_as_secondary_evidence is False
    assert doc.exclude_from_drafting is True
    assert is_authoritative_evidence(doc) is False


def test_template_excluded_from_evidence() -> None:
    doc = _doc(DocumentClassification.TEMPLATE)
    apply_authority_defaults(doc)
    assert is_authoritative_evidence(doc) is False


def test_secondary_enable_allows_comparison_only() -> None:
    doc = _doc(DocumentClassification.EXISTING_DEMAND)
    apply_authority_defaults(doc)
    doc.treat_as_secondary_evidence = True
    # Secondary is comparison-only — never primary authoritative evidence
    assert doc.exclude_from_drafting is True
    assert is_authoritative_evidence(doc) is False


def test_police_is_authoritative() -> None:
    doc = _doc(DocumentClassification.POLICE_REPORT)
    assert is_authoritative_evidence(doc) is True


def test_secondary_only_for_existing_demand() -> None:
    doc = _doc(DocumentClassification.POLICE_REPORT)
    try:
        validate_authority_patch(doc, treat_as_secondary_evidence=True)
        raise AssertionError("expected DomainError")
    except DomainError as exc:
        assert exc.error_code == "document_invalid_patch"
