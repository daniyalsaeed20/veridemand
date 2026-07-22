"""Generic, language-neutral text-structure quality metrics."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from backend.app.extraction.native.models import RawCharCandidate, RawWordCandidate

_CID_RE = re.compile(r"\(cid:\d+\)", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"^[\W_]+$", re.UNICODE)
_ALNUM_RE = re.compile(r"[0-9A-Za-z\u00C0-\u024F]")


@dataclass(frozen=True, slots=True)
class TextStructureMetrics:
    word_count: int
    character_count: int
    single_character_word_ratio: float
    symbol_only_word_ratio: float
    alphanumeric_word_ratio: float
    cid_token_ratio: float
    very_long_token_ratio: float
    repeated_token_ratio: float
    font_count: int
    missing_font_ratio: float
    upright_character_ratio: float
    extraction_order_backtrack_ratio: float
    characters_per_page_area: float
    words_per_page_area: float


def analyse_text_structure(
    characters: list[RawCharCandidate],
    words: list[RawWordCandidate],
    *,
    page_width: float,
    page_height: float,
) -> TextStructureMetrics:
    word_count = len(words)
    character_count = len(characters)
    area = max(page_width * page_height, 1.0)

    if word_count == 0:
        single = symbol = alnum = cid = long = repeated = 0.0
    else:
        single_n = sum(1 for w in words if len(w.text) == 1)
        symbol_n = sum(1 for w in words if _SYMBOL_RE.match(w.text) is not None)
        alnum_n = sum(1 for w in words if _ALNUM_RE.search(w.text) is not None)
        cid_n = sum(1 for w in words if _CID_RE.search(w.text) is not None)
        long_n = sum(1 for w in words if len(w.text) > 40)
        counts = Counter(w.text for w in words)
        repeated_n = sum(1 for w in words if counts[w.text] >= 3)
        single = single_n / word_count
        symbol = symbol_n / word_count
        alnum = alnum_n / word_count
        cid = cid_n / word_count
        long = long_n / word_count
        repeated = repeated_n / word_count

    fonts = {c.fontname for c in characters if c.fontname}
    missing = sum(1 for c in characters if not c.fontname) / max(character_count, 1)
    upright = sum(1 for c in characters if c.upright) / max(character_count, 1)

    backtracks = 0
    for i in range(1, len(characters)):
        prev = characters[i - 1]
        cur = characters[i]
        # Significant leftward jump on roughly the same baseline.
        if cur.x0 + 2.0 < prev.x0 and abs(cur.top - prev.top) < 4.0:
            backtracks += 1
    backtrack_ratio = backtracks / max(character_count, 1)

    return TextStructureMetrics(
        word_count=word_count,
        character_count=character_count,
        single_character_word_ratio=single,
        symbol_only_word_ratio=symbol,
        alphanumeric_word_ratio=alnum,
        cid_token_ratio=cid,
        very_long_token_ratio=long,
        repeated_token_ratio=repeated,
        font_count=len(fonts),
        missing_font_ratio=missing,
        upright_character_ratio=upright,
        extraction_order_backtrack_ratio=backtrack_ratio,
        characters_per_page_area=character_count / area,
        words_per_page_area=word_count / area,
    )
