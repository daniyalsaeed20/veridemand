"""Privacy-safe routing metrics helpers."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("veridemand.routing.metrics")


def log_page_route_decision(
    *,
    document_id: str,
    page_number: int,
    route: str,
    reason_codes: list[str],
    native_word_count: int,
    visual_agreement_score: float | None,
    sample_count: int,
    recognition_agreement_score: float | None,
    full_ocr_required: bool,
    primary_limit_side: int | None = None,
    fallback_used: bool | None = None,
    route_duration_ms: int | None = None,
    render_duration_ms: int | None = None,
    ocr_duration_ms: int | None = None,
    page_total_duration_ms: int | None = None,
) -> None:
    """Log a page route decision without text, paths, or filenames."""

    extra: dict[str, Any] = {
        "event": "page_route_decision",
        "document_id": document_id,
        "page_number": page_number,
        "route": route,
        "reason_codes": list(reason_codes),
        "native_word_count": native_word_count,
        "visual_agreement_score": visual_agreement_score,
        "sample_count": sample_count,
        "recognition_agreement_score": recognition_agreement_score,
        "full_ocr_required": full_ocr_required,
        "primary_limit_side": primary_limit_side,
        "fallback_used": fallback_used,
        "route_duration_ms": route_duration_ms,
        "render_duration_ms": render_duration_ms,
        "ocr_duration_ms": ocr_duration_ms,
        "page_total_duration_ms": page_total_duration_ms,
    }
    logger.info("page_route_decision", extra=extra)
