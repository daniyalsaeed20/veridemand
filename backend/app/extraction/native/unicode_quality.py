"""Unicode quality metrics for native character candidates."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from backend.app.extraction.native.models import RawCharCandidate


@dataclass(frozen=True, slots=True)
class UnicodeMetrics:
    replacement_character_ratio: float
    control_character_ratio: float
    private_use_character_ratio: float
    unassigned_character_ratio: float
    noncharacter_ratio: float
    unprintable_character_ratio: float
    whitespace_ratio: float
    sample_categories: list[str]


def _is_noncharacter(cp: int) -> bool:
    if 0xFDD0 <= cp <= 0xFDEF:
        return True
    return (cp & 0xFFFE) == 0xFFFE and 0 <= cp <= 0x10FFFF


def _is_unassigned(ch: str) -> bool:
    return unicodedata.category(ch) == "Cn"


def analyse_unicode(characters: list[RawCharCandidate]) -> UnicodeMetrics:
    """Analyse non-whitespace characters for Unicode quality ratios."""

    if not characters:
        return UnicodeMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, [])

    non_ws = [c for c in characters if not c.text.isspace()]
    total = max(len(non_ws), 1)
    whitespace_ratio = (len(characters) - len(non_ws)) / max(len(characters), 1)

    replacement = 0
    control = 0
    private_use = 0
    unassigned = 0
    noncharacter = 0
    unprintable = 0
    categories: list[str] = []

    for cand in non_ws:
        ch = cand.text
        cat = unicodedata.category(ch)
        categories.append(cat)
        cp = ord(ch)
        if ch == "\ufffd":
            replacement += 1
        if cat == "Cc":
            control += 1
        if cat == "Co":
            private_use += 1
        if _is_unassigned(ch):
            unassigned += 1
        if _is_noncharacter(cp):
            noncharacter += 1
        if cat == "Cs" or (not ch.isprintable() and not ch.isspace() and cat != "Cf"):
            unprintable += 1

    return UnicodeMetrics(
        replacement_character_ratio=replacement / total,
        control_character_ratio=control / total,
        private_use_character_ratio=private_use / total,
        unassigned_character_ratio=unassigned / total,
        noncharacter_ratio=noncharacter / total,
        unprintable_character_ratio=unprintable / total,
        whitespace_ratio=whitespace_ratio,
        sample_categories=categories[:32],
    )


def unicode_category_for(text: str) -> str:
    if not text:
        return "Cn"
    return unicodedata.category(text[0])


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)
