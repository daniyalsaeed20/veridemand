"""Unit tests for near-overprint pairing and layer selection."""

from __future__ import annotations

from backend.app.extraction.native.models import RawCharCandidate
from backend.app.extraction.native.near_overprint import (
    analyse_and_clean_near_overprint,
    rebuild_words_from_characters,
)


def _ch(
    text: str,
    *,
    x0: float,
    top: float,
    size: float = 12.0,
    font: str = "Helvetica",
    seq: int = 0,
    width: float | None = None,
    tagged: bool | None = None,
) -> RawCharCandidate:
    w = width if width is not None else size * 0.55
    return RawCharCandidate(
        text=text,
        fontname=font,
        size=size,
        upright=True,
        rotation_degrees=0.0,
        x0=x0,
        x1=x0 + w,
        top=top,
        bottom=top + size,
        sequence_index=seq,
        tagged=tagged,
    )


def test_interleaved_near_overprint_rruunn_style() -> None:
    """Interleaved duplicate glyphs in reading order must clean or reject."""

    chars: list[RawCharCandidate] = []
    seq = 0
    for i, c in enumerate("Patient"):
        chars.append(_ch(c, x0=10 + i * 7, top=20, size=12, font="F1", seq=seq))
        seq += 1
        chars.append(_ch(c, x0=11 + i * 7, top=21, size=11.5, font="F2", seq=seq))
        seq += 1
    # Reading order is already Helvetica then Times per glyph slot when sorted by x.
    outcome = analyse_and_clean_near_overprint(chars, strict_duplicate_ratio=0.0, words=[])
    assert outcome.selection in {"cleaned", "ambiguous"}
    if outcome.selection == "cleaned":
        assert "".join(c.text for c in outcome.characters) == "Patient"
    else:
        assert outcome.characters == []

    # "letter" — two 't' glyphs spaced normally.
    chars = [
        _ch("l", x0=10, top=20, seq=0),
        _ch("e", x0=17, top=20, seq=1),
        _ch("t", x0=24, top=20, seq=2),
        _ch("t", x0=31, top=20, seq=3),
        _ch("e", x0=38, top=20, seq=4),
        _ch("r", x0=45, top=20, seq=5),
    ]
    outcome = analyse_and_clean_near_overprint(
        chars, strict_duplicate_ratio=0.0, words=rebuild_words_from_characters(chars)
    )
    assert outcome.selection == "none"
    assert outcome.metrics.near_overprint_duplicate_ratio < 0.20
    assert len(outcome.characters) == 6


def test_cross_font_near_overprint_cleans_or_rejects() -> None:
    line = "RunSample"
    chars: list[RawCharCandidate] = []
    seq = 0
    for i, c in enumerate(line):
        chars.append(_ch(c, x0=10 + i * 8, top=20, size=14, font="Helvetica", seq=seq))
        seq += 1
    for i, c in enumerate(line):
        chars.append(_ch(c, x0=11.5 + i * 8, top=21.5, size=13.5, font="Times-Roman", seq=seq))
        seq += 1
    outcome = analyse_and_clean_near_overprint(
        chars, strict_duplicate_ratio=0.0, words=rebuild_words_from_characters(chars)
    )
    assert outcome.selection in {"cleaned", "ambiguous"}
    if outcome.selection == "cleaned":
        assert len(outcome.characters) == len(line)
        text = "".join(c.text for c in outcome.characters)
        assert text == line
        assert all(w.text for w in outcome.words)
        # Residual after clean must be low; pre-clean participation was high.
        assert outcome.metrics.near_overprint_duplicate_ratio <= 0.20
    else:
        assert outcome.characters == []


def test_high_near_overprint_never_returns_full_double_layer() -> None:
    chars: list[RawCharCandidate] = []
    seq = 0
    for i, c in enumerate("ABCDEFGHIJ"):
        chars.append(_ch(c, x0=10 + i * 9, top=20, font="Helvetica", seq=seq))
        seq += 1
        chars.append(_ch(c, x0=11.5 + i * 9, top=21.5, font="Times-Roman", seq=seq))
        seq += 1
    outcome = analyse_and_clean_near_overprint(chars, strict_duplicate_ratio=0.0, words=[])
    assert outcome.selection in {"cleaned", "ambiguous"}
    assert len(outcome.characters) <= 11
