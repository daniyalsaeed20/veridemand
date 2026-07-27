"""Embedded OCR candidate classification (Route B entry)."""

from __future__ import annotations

from backend.app.contracts.native import NativePageDecision, NativePageResult, SourceMode
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.routing.models import RoutingPolicy


def page_is_image_dominant(page: NativePageResult) -> bool:
    """Whether native diagnostics flagged the page as image-dominant."""

    codes = {str(c) for c in (page.trust.reason_codes or [])}
    if NativeReasonCode.IMAGE_DOMINANT_PAGE.value in codes:
        return True
    if "image_dominant_page" in codes:
        return True
    # Image authority without accepted digital native text.
    return page.source_mode is SourceMode.IMAGE_AUTHORITY


def is_embedded_ocr_candidate(page: NativePageResult, policy: RoutingPolicy) -> bool:
    """Image-dominant (or rejected-as-visual) page that still has substantial native text.

    Image dominance alone must NOT force full OCR — this flags the page for
    visual/recognition agreement checks first.
    """

    words = page.words or []
    chars = page.characters or []
    has_substantial_text = (
        len(words) >= policy.min_native_words or len(chars) >= policy.min_native_characters
    )
    if not has_substantial_text:
        return False

    image_dominant = page_is_image_dominant(page)
    # Accepted natives that are image-dominant, or pages with native text present
    # despite visual_processing_required / rejection for image reasons.
    if image_dominant and (
        page.decision is NativePageDecision.ACCEPTED
        or page.trust.visual_processing_required
        or page.decision
        in {
            NativePageDecision.REJECTED,
            NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION,
        }
    ):
        # Need actual text payload available for agreement checks.
        if page.decision is NativePageDecision.ACCEPTED and words:
            return True
        # Rejected/suppressed pages may have had text stripped — only candidate
        # when words remain (pre-suppress) or character counts recorded.
        if words:
            return True
        metrics_words = page.trust.metrics.word_count
        if metrics_words >= policy.min_native_words and not words:
            # Text was stripped; cannot verify embedded layer without boxes.
            return False
    return False
