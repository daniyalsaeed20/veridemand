"""Helpers for selecting native word boxes during Phase 4.5 routing."""

from __future__ import annotations

from backend.app.contracts.native import NativePageResult, NativeWord


def native_words_for_routing(page: NativePageResult) -> list[NativeWord]:
    """Accepted words when present; otherwise diagnostic verification candidates.

    Route A (digital native) must continue to use ``page.words`` only.
    Route B / repair / full-OCR gates use this helper so rejected/suppressed
    pages can still verify an embedded OCR layer.
    """

    words = page.words or []
    if words:
        return list(words)
    return list(page.verification_words or [])
