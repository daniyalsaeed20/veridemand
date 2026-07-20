"""Authority and page-quality gates for fact extraction inputs."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.enums import (
    ClassificationStatus,
    DocumentClassification,
    DocumentStatus,
    PageRoute,
    SafetyArchetype,
)
from app.models.source_span import SourceSpan
from app.services.classification.authority import is_primary_authoritative

_NON_USABLE_FLAGS = frozenset(
    {
        "insufficient_coverage",
        "awaiting_ocr",
        "broken_text_layer",
        "pathological_tokenization",
    }
)


@dataclass(frozen=True)
class DocumentEligibility:
    eligible: bool
    secondary: bool
    suppressed_reason: str | None
    classification_ambiguous: bool


def document_eligibility(document: Document) -> DocumentEligibility:
    ambiguous = document.classification_status in {
        ClassificationStatus.AMBIGUOUS,
        ClassificationStatus.NEEDS_CONFIRMATION,
        ClassificationStatus.PROPOSED,
    }

    if document.status == DocumentStatus.EXCLUDED:
        return DocumentEligibility(False, False, "excluded", ambiguous)

    if document.classification == DocumentClassification.TEMPLATE or (
        document.safety_archetype == SafetyArchetype.TEMPLATE
    ):
        return DocumentEligibility(False, False, "template", ambiguous)

    if document.safety_archetype == SafetyArchetype.UNCERTAIN_DERIVATIVE:
        return DocumentEligibility(False, False, "uncertain_derivative", ambiguous)

    if is_primary_authoritative(document):
        return DocumentEligibility(True, False, None, ambiguous)

    # Explicit secondary existing-demand path (comparison suggestions only)
    is_demand = (
        document.classification == DocumentClassification.EXISTING_DEMAND
        or document.safety_archetype == SafetyArchetype.EXISTING_DEMAND
    )
    if is_demand and document.treat_as_secondary_evidence:
        return DocumentEligibility(True, True, None, True)

    return DocumentEligibility(False, False, "authority_excluded", ambiguous)


def page_is_usable(page: DocumentPage) -> bool:
    if page.ocr_status == "failed":
        return False
    if any(f in _NON_USABLE_FLAGS for f in page.quality_flags):
        return False
    if page.route == PageRoute.MANUAL_REVIEW and page.token_count in (0, None):
        return False
    return True


def page_quality_weak(page: DocumentPage) -> bool:
    if "low_confidence" in page.quality_flags:
        return True
    if page.ocr_status == "failed":
        return True
    return False


def filter_usable_spans(
    pages: list[DocumentPage],
    spans_by_page: dict[int, list[SourceSpan]],
) -> tuple[dict[int, list[SourceSpan]], int, int]:
    """Return (usable_spans, pages_suppressed, spans_count)."""
    usable: dict[int, list[SourceSpan]] = {}
    suppressed = 0
    span_count = 0
    for page in pages:
        page_spans = spans_by_page.get(page.page_number, [])
        if not page_is_usable(page):
            suppressed += 1
            continue
        if not page_spans:
            continue
        usable[page.page_number] = list(page_spans)
        span_count += len(page_spans)
    return usable, suppressed, span_count
