"""Embedded OCR candidate classification (Route B entry)."""

from __future__ import annotations

from backend.app.contracts.native import NativePageDecision, NativePageResult, SourceMode
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.native_words import native_words_for_routing


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

    words = native_words_for_routing(page)
    chars = page.characters or []
    has_substantial_text = (
        len(words) >= policy.min_native_words or len(chars) >= policy.min_native_characters
    )
    if not has_substantial_text:
        # Metrics alone are insufficient without boxes for agreement probes.
        metrics_words = page.trust.metrics.word_count
        if metrics_words >= policy.min_native_words and not words:
            return False
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
        return bool(words)
    return False
