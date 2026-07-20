"""FR-CLS-06 authority policy — independent of winning taxonomy category."""

from __future__ import annotations

from app.core.domain_errors import DomainError
from app.models.document import Document
from app.models.enums import DocumentClassification, DocumentStatus, SafetyArchetype
from app.models.taxonomies import ErrorCode
from app.services.classification.types import AuthorityMode

_SAFETY_RESTRICTED = frozenset(
    {
        SafetyArchetype.EXISTING_DEMAND,
        SafetyArchetype.TEMPLATE,
        SafetyArchetype.UNCERTAIN_DERIVATIVE,
    }
)


def safety_restricts_primary(archetype: SafetyArchetype | None) -> bool:
    return archetype is not None and archetype in _SAFETY_RESTRICTED


def authority_mode_for(document: Document) -> AuthorityMode:
    if safety_restricts_primary(document.safety_archetype):
        if (
            document.classification == DocumentClassification.EXISTING_DEMAND
            and document.treat_as_secondary_evidence
            and not document.exclude_from_drafting
        ):
            return AuthorityMode.SECONDARY_ENABLED
        return AuthorityMode.SECONDARY_DISABLED
    if document.classification == DocumentClassification.EXISTING_DEMAND:
        if document.treat_as_secondary_evidence:
            return AuthorityMode.SECONDARY_ENABLED
        return AuthorityMode.SECONDARY_DISABLED
    if document.classification == DocumentClassification.TEMPLATE:
        return AuthorityMode.SECONDARY_DISABLED
    if document.exclude_from_drafting or document.status == DocumentStatus.EXCLUDED:
        return AuthorityMode.SECONDARY_DISABLED
    return AuthorityMode.AUTHORITATIVE


def apply_authority_policy(
    document: Document,
    *,
    archetype: SafetyArchetype | None = None,
    preserve_user_exclude: bool = False,
    preserve_secondary: bool = False,
) -> None:
    """Apply non-authoritative defaults from safety archetype and/or category.

    Classification-independent invariant: material demand/template/derivative
    signals force exclude_from_drafting unless an explicit allowed secondary path.
    """
    arch = archetype if archetype is not None else document.safety_archetype
    if arch is not None:
        document.safety_archetype = arch

    prior_exclude = document.exclude_from_drafting
    prior_secondary = document.treat_as_secondary_evidence

    if safety_restricts_primary(document.safety_archetype):
        document.exclude_from_drafting = True
        if document.safety_archetype == SafetyArchetype.TEMPLATE:
            document.treat_as_secondary_evidence = False
        elif document.safety_archetype == SafetyArchetype.UNCERTAIN_DERIVATIVE:
            document.treat_as_secondary_evidence = False
        else:
            # existing_demand archetype: secondary stays false until user enables
            if not preserve_secondary:
                document.treat_as_secondary_evidence = False
        if preserve_user_exclude and prior_exclude:
            document.exclude_from_drafting = True
        return

    # No safety restriction — category-based defaults for demand/template labels
    if document.classification == DocumentClassification.EXISTING_DEMAND:
        if not preserve_secondary:
            document.treat_as_secondary_evidence = False
        document.exclude_from_drafting = True
    elif document.classification == DocumentClassification.TEMPLATE:
        document.treat_as_secondary_evidence = False
        document.exclude_from_drafting = True
    elif not preserve_user_exclude:
        # Ordinary evidence: leave exclude as-is unless freshly classified
        pass

    if preserve_user_exclude and prior_exclude:
        document.exclude_from_drafting = True
    if preserve_secondary and prior_secondary:
        document.treat_as_secondary_evidence = prior_secondary


def apply_authority_defaults(document: Document) -> None:
    """Backward-compatible wrapper used by older call sites."""
    apply_authority_policy(document, archetype=document.safety_archetype)


def validate_authority_patch(
    document: Document,
    *,
    treat_as_secondary_evidence: bool | None,
    exclude_from_drafting: bool | None = None,
) -> None:
    if treat_as_secondary_evidence is None and exclude_from_drafting is None:
        return

    if treat_as_secondary_evidence:
        if document.classification != DocumentClassification.EXISTING_DEMAND:
            raise DomainError(
                ErrorCode.DOCUMENT_INVALID_PATCH,
                details={"field": "treat_as_secondary_evidence", "reason": "not_existing_demand"},
                document_id=document.id,
                session_id=document.session_id,
            )
        if document.safety_archetype == SafetyArchetype.TEMPLATE:
            raise DomainError(
                ErrorCode.DOCUMENT_INVALID_PATCH,
                details={"field": "treat_as_secondary_evidence", "reason": "template_forbidden"},
                document_id=document.id,
                session_id=document.session_id,
            )

    # Clearing exclusion while safety-restricted without secondary path is OK
    # (document remains non-primary via is_authoritative_evidence), but enabling
    # primary use is blocked by is_authoritative_evidence / assert_authority_invariant.


def is_primary_authoritative(document: Document) -> bool:
    """True only for ordinary evidence eligible as primary Fact sources later."""
    if document.exclude_from_drafting:
        return False
    if document.status == DocumentStatus.EXCLUDED:
        return False
    if safety_restricts_primary(document.safety_archetype):
        return False
    if document.classification in {
        DocumentClassification.EXISTING_DEMAND,
        DocumentClassification.TEMPLATE,
    }:
        return False
    return True


def is_authoritative_evidence(document: Document) -> bool:
    """Spans may feed future extraction only as primary or explicit secondary.

    Secondary-enabled existing demands return True for comparison use but are
    never primary; callers must also check classification / treat_as_secondary.
    """
    if document.exclude_from_drafting:
        return False
    if document.status == DocumentStatus.EXCLUDED:
        return False
    if document.safety_archetype == SafetyArchetype.TEMPLATE:
        return False
    if document.safety_archetype == SafetyArchetype.UNCERTAIN_DERIVATIVE:
        return False
    if (
        document.safety_archetype == SafetyArchetype.EXISTING_DEMAND
        or document.classification == DocumentClassification.EXISTING_DEMAND
    ):
        return bool(document.treat_as_secondary_evidence)
    if document.classification == DocumentClassification.TEMPLATE:
        return False
    return True


def assert_authority_invariant(document: Document) -> None:
    """Reject impossible primary+safety combinations."""
    if safety_restricts_primary(document.safety_archetype) and is_primary_authoritative(document):
        raise DomainError(
            ErrorCode.DOCUMENT_INVALID_PATCH,
            details={"reason": "safety_primary_invariant"},
            document_id=document.id,
            session_id=document.session_id,
        )


def enforce_authority_invariant(document: Document) -> None:
    """Normalize rather than raise when auto-path would violate invariant."""
    if not safety_restricts_primary(document.safety_archetype):
        return
    if document.safety_archetype in {
        SafetyArchetype.TEMPLATE,
        SafetyArchetype.UNCERTAIN_DERIVATIVE,
    }:
        document.exclude_from_drafting = True
        document.treat_as_secondary_evidence = False
        return
    # existing_demand archetype: keep excluded unless secondary explicitly enabled
    if not document.treat_as_secondary_evidence:
        document.exclude_from_drafting = True
