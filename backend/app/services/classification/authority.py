"""FR-CLS-06 authority guard for existing demands and templates."""

from __future__ import annotations

from app.core.domain_errors import DomainError
from app.models.document import Document
from app.models.enums import DocumentClassification, DocumentStatus
from app.models.taxonomies import ErrorCode
from app.services.classification.types import AuthorityMode


def authority_mode_for(document: Document) -> AuthorityMode:
    if document.classification == DocumentClassification.EXISTING_DEMAND:
        if document.treat_as_secondary_evidence:
            return AuthorityMode.SECONDARY_ENABLED
        return AuthorityMode.SECONDARY_DISABLED
    if document.classification == DocumentClassification.TEMPLATE:
        return AuthorityMode.SECONDARY_DISABLED
    return AuthorityMode.AUTHORITATIVE


def apply_authority_defaults(document: Document) -> None:
    """Apply non-authoritative defaults after automatic classification."""
    if document.classification == DocumentClassification.EXISTING_DEMAND:
        document.treat_as_secondary_evidence = False
        document.exclude_from_drafting = True
    elif document.classification == DocumentClassification.TEMPLATE:
        document.treat_as_secondary_evidence = False
        document.exclude_from_drafting = True


def validate_authority_patch(
    document: Document,
    *,
    treat_as_secondary_evidence: bool | None,
) -> None:
    if treat_as_secondary_evidence is None:
        return
    if (
        treat_as_secondary_evidence
        and document.classification != DocumentClassification.EXISTING_DEMAND
    ):
        raise DomainError(
            ErrorCode.DOCUMENT_INVALID_PATCH,
            details={"field": "treat_as_secondary_evidence"},
            document_id=document.id,
            session_id=document.session_id,
        )


def is_authoritative_evidence(document: Document) -> bool:
    """True when document may supply spans to future deterministic fact extraction."""
    if document.exclude_from_drafting:
        return False
    if document.classification in {
        DocumentClassification.EXISTING_DEMAND,
        DocumentClassification.TEMPLATE,
    }:
        return document.treat_as_secondary_evidence
    if document.status == DocumentStatus.EXCLUDED:
        return False
    return True
