"""Unicode quality metrics for native character candidates."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from backend.app.extraction.native.models import RawCharCandidate

# Common checkbox / form-mark code points (Ballot Box family + related).
_CHECKBOX_LIKE = frozenset(
    {
        0x2610,  # ☐ BALLOT BOX
        0x2611,  # ☑ BALLOT BOX WITH CHECK
        0x2612,  # ☒ BALLOT BOX WITH X
        0x25A1,  # □ WHITE SQUARE
        0x25A0,  # ■ BLACK SQUARE
        0x25FB,  # ◻ WHITE MEDIUM SQUARE
        0x25FC,  # ◼ BLACK MEDIUM SQUARE
        0x2B1C,  # ⬜ WHITE LARGE SQUARE
        0x2B1B,  # ⬛ BLACK LARGE SQUARE
        0x2713,  # ✓ CHECK MARK
        0x2714,  # ✔ HEAVY CHECK MARK
        0x2717,  # ✗ BALLOT X
        0x2718,  # ✘ HEAVY BALLOT X
    }
)

# Dingbat block and common ornamental ranges (counts only; no string exposure).
_DINGBAT_RANGES = (
    (0x2700, 0x27BF),  # Dingbats
    (0x1F300, 0x1F5FF),  # Misc Symbols and Pictographs (subset used as marks)
)


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


@dataclass(frozen=True, slots=True)
class ExtendedUnicodeMetrics:
    """Extended Unicode counts/ratios for Correction 3 diagnostics (no strings)."""

    non_whitespace_total: int
    replacement_count: int
    control_count: int
    private_use_count: int
    unassigned_count: int
    noncharacter_count: int
    unprintable_count: int
    surrogate_count: int
    format_count: int
    symbol_count: int
    punctuation_count: int
    checkbox_like_count: int
    dingbat_like_count: int
    replacement_character_ratio: float
    control_character_ratio: float
    private_use_character_ratio: float
    unassigned_character_ratio: float
    noncharacter_ratio: float
    unprintable_character_ratio: float
    surrogate_character_ratio: float
    format_character_ratio: float
    symbol_character_ratio: float
    punctuation_character_ratio: float
    checkbox_like_ratio: float
    dingbat_like_ratio: float


def _is_noncharacter(cp: int) -> bool:
    if 0xFDD0 <= cp <= 0xFDEF:
        return True
    return (cp & 0xFFFE) == 0xFFFE and 0 <= cp <= 0x10FFFF


def _is_unassigned(ch: str) -> bool:
    return unicodedata.category(ch) == "Cn"


def _is_dingbat_like(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _DINGBAT_RANGES)


def _is_checkbox_like(cp: int, cat: str) -> bool:
    if cp in _CHECKBOX_LIKE:
        return True
    # Private-use single-glyph form marks are often checkbox stand-ins.
    return cat == "Co" and True  # counted separately; caller may refine


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


def analyse_unicode_extended(characters: list[RawCharCandidate]) -> ExtendedUnicodeMetrics:
    """Extended Unicode counts for glyph quarantine diagnostics (no strings)."""

    if not characters:
        return ExtendedUnicodeMetrics(
            non_whitespace_total=0,
            replacement_count=0,
            control_count=0,
            private_use_count=0,
            unassigned_count=0,
            noncharacter_count=0,
            unprintable_count=0,
            surrogate_count=0,
            format_count=0,
            symbol_count=0,
            punctuation_count=0,
            checkbox_like_count=0,
            dingbat_like_count=0,
            replacement_character_ratio=0.0,
            control_character_ratio=0.0,
            private_use_character_ratio=0.0,
            unassigned_character_ratio=0.0,
            noncharacter_ratio=0.0,
            unprintable_character_ratio=0.0,
            surrogate_character_ratio=0.0,
            format_character_ratio=0.0,
            symbol_character_ratio=0.0,
            punctuation_character_ratio=0.0,
            checkbox_like_ratio=0.0,
            dingbat_like_ratio=0.0,
        )

    non_ws = [c for c in characters if not c.text.isspace()]
    total = max(len(non_ws), 1)

    replacement = 0
    control = 0
    private_use = 0
    unassigned = 0
    noncharacter = 0
    unprintable = 0
    surrogate = 0
    format_c = 0
    symbol = 0
    punctuation = 0
    checkbox_like = 0
    dingbat_like = 0

    for cand in non_ws:
        ch = cand.text
        cat = unicodedata.category(ch)
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
        if cat == "Cs":
            surrogate += 1
        if cat == "Cf":
            format_c += 1
        if cat.startswith("S"):
            symbol += 1
        if cat.startswith("P"):
            punctuation += 1
        if cat == "Cs" or (not ch.isprintable() and not ch.isspace() and cat != "Cf"):
            unprintable += 1
        if cp in _CHECKBOX_LIKE:
            checkbox_like += 1
        elif cat == "Co" and len(ch) == 1:
            # Isolated private-use often stands in for form checkboxes.
            checkbox_like += 1
        if _is_dingbat_like(cp):
            dingbat_like += 1

    return ExtendedUnicodeMetrics(
        non_whitespace_total=len(non_ws),
        replacement_count=replacement,
        control_count=control,
        private_use_count=private_use,
        unassigned_count=unassigned,
        noncharacter_count=noncharacter,
        unprintable_count=unprintable,
        surrogate_count=surrogate,
        format_count=format_c,
        symbol_count=symbol,
        punctuation_count=punctuation,
        checkbox_like_count=checkbox_like,
        dingbat_like_count=dingbat_like,
        replacement_character_ratio=replacement / total,
        control_character_ratio=control / total,
        private_use_character_ratio=private_use / total,
        unassigned_character_ratio=unassigned / total,
        noncharacter_ratio=noncharacter / total,
        unprintable_character_ratio=unprintable / total,
        surrogate_character_ratio=surrogate / total,
        format_character_ratio=format_c / total,
        symbol_character_ratio=symbol / total,
        punctuation_character_ratio=punctuation / total,
        checkbox_like_ratio=checkbox_like / total,
        dingbat_like_ratio=dingbat_like / total,
    )


def unicode_category_for(text: str) -> str:
    if not text:
        return "Cn"
    return unicodedata.category(text[0])


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def char_is_invalid_for_quarantine(ch: str) -> tuple[bool, str]:
    """Return (is_invalid, unicode_category) for glyph quarantine eligibility."""

    if not ch or ch.isspace():
        return False, "Zs"
    cat = unicodedata.category(ch)
    cp = ord(ch)
    if ch == "\ufffd":
        return True, cat
    if cat in {"Cc", "Co", "Cn", "Cs"}:
        return True, cat
    if _is_noncharacter(cp):
        return True, cat
    if cat == "Cs" or (not ch.isprintable() and not ch.isspace() and cat != "Cf"):
        return True, cat
    return False, cat
