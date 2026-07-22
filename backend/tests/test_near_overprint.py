"""Unit tests for near-overprint pairing, composite evidence, and hard reject."""

from __future__ import annotations

from backend.app.contracts.native import NativePageDecision
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import (
    NativeTrustPolicyConfig,
    PageExtractionCandidate,
    RawCharCandidate,
)
from backend.app.extraction.native.near_overprint import (
    CompositeThresholds,
    NearOverprintMetrics,
    analyse_and_clean_near_overprint,
    composite_duplicate_layer_evidence,
    interleaved_double_ratio,
    rebuild_words_from_characters,
)
from backend.app.extraction.native.trust_policy import decide_page_trust


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


def _double_line(text: str, *, top: float = 20.0) -> list[RawCharCandidate]:
    chars: list[RawCharCandidate] = []
    seq = 0
    for i, c in enumerate(text):
        chars.append(_ch(c, x0=10 + i * 8, top=top, size=14, font="Helvetica", seq=seq))
        seq += 1
    for i, c in enumerate(text):
        chars.append(_ch(c, x0=11.5 + i * 8, top=top + 1.5, size=13.5, font="Times-Roman", seq=seq))
        seq += 1
    return chars


def test_interleaved_near_overprint_rruunn_style() -> None:
    chars = _double_line("PatientNameHere")
    outcome = analyse_and_clean_near_overprint(chars, strict_duplicate_ratio=0.0, words=[])
    assert outcome.selection in {"cleaned", "ambiguous"}
    if outcome.selection == "cleaned":
        assert "".join(c.text for c in outcome.characters) == "PatientNameHere"
        assert interleaved_double_ratio("".join(c.text for c in outcome.characters)) < 0.35
    else:
        assert outcome.characters == []


def test_legitimate_adjacent_repeats_not_near_overprint() -> None:
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
    assert not outcome.metrics.composite_duplicate_layer_evidence
    assert len(outcome.characters) == 6


def test_cross_font_near_overprint_cleans_or_rejects() -> None:
    line = "RunSampleTextXX"
    chars = _double_line(line)
    outcome = analyse_and_clean_near_overprint(
        chars, strict_duplicate_ratio=0.0, words=rebuild_words_from_characters(chars)
    )
    assert outcome.selection in {"cleaned", "ambiguous"}
    assert outcome.metrics.composite_duplicate_layer_evidence
    if outcome.selection == "cleaned":
        assert "".join(c.text for c in outcome.characters) == line
    else:
        assert outcome.characters == []


def test_high_near_overprint_never_returns_full_double_layer() -> None:
    chars = _double_line("ABCDEFGHIJKLMNOP")
    outcome = analyse_and_clean_near_overprint(chars, strict_duplicate_ratio=0.0, words=[])
    assert outcome.selection in {"cleaned", "ambiguous"}
    assert len(outcome.characters) <= len("ABCDEFGHIJKLMNOP")


def test_composite_hard_reject_overrides_high_weighted_score() -> None:
    """Soft duplication weight alone cannot accept when composite evidence is set."""

    policy = NativeTrustPolicyConfig()
    # Enough good text that weighted score would stay above threshold if soft-only.
    chars = _double_line("ABCDEFGHIJKLMNOPQRSTUVWXYZ012345")
    outcome = analyse_and_clean_near_overprint(chars, strict_duplicate_ratio=0.0, words=[])
    assert outcome.metrics.composite_duplicate_layer_evidence

    if outcome.selection == "cleaned":
        page = PageExtractionCandidate(
            page_number=1,
            page_width=612,
            page_height=792,
            page_bbox_x0=0,
            page_bbox_top=0,
            raw_character_count=len(chars),
            characters=outcome.characters,
            words=outcome.words,
            images=[],
            page_dimension_match=True,
            strict_duplicate_ratio=0.0,
            near_overprint_duplicate_ratio=outcome.metrics.near_overprint_duplicate_ratio,
            duplicate_layer_count=outcome.metrics.duplicate_layer_count,
            dominant_duplicate_offset_x=outcome.metrics.dominant_duplicate_offset_x,
            dominant_duplicate_offset_y=outcome.metrics.dominant_duplicate_offset_y,
            duplicate_layer_coverage_ratio=outcome.metrics.duplicate_layer_coverage_ratio,
            matched_near_duplicate_count=outcome.metrics.matched_near_duplicate_count,
            dominant_offset_support_ratio=outcome.metrics.dominant_offset_support_ratio,
            matched_word_span=outcome.metrics.matched_word_span,
            matched_line_span=outcome.metrics.matched_line_span,
            near_overprint_composite_evidence=True,
            near_overprint_cleaned=True,
            near_overprint_ambiguous=False,
        )
        metrics, g, u, t, im = build_page_metrics(page, policy)
        bundle = decide_page_trust(
            page,
            metrics=metrics,
            geometry_m=g,
            unicode_m=u,
            text_m=t,
            image_m=im,
            policy=policy,
            source_type="pdf",
        )
        assert bundle.accept_text
        assert interleaved_double_ratio(" ".join(w.text for w in page.words)) < 0.35
    else:
        page = PageExtractionCandidate(
            page_number=1,
            page_width=612,
            page_height=792,
            page_bbox_x0=0,
            page_bbox_top=0,
            raw_character_count=len(chars),
            characters=[],
            words=[],
            images=[],
            page_dimension_match=True,
            strict_duplicate_ratio=0.0,
            near_overprint_duplicate_ratio=outcome.metrics.near_overprint_duplicate_ratio,
            duplicate_layer_count=2,
            dominant_duplicate_offset_x=outcome.metrics.dominant_duplicate_offset_x,
            dominant_duplicate_offset_y=outcome.metrics.dominant_duplicate_offset_y,
            duplicate_layer_coverage_ratio=outcome.metrics.duplicate_layer_coverage_ratio,
            matched_near_duplicate_count=outcome.metrics.matched_near_duplicate_count,
            dominant_offset_support_ratio=outcome.metrics.dominant_offset_support_ratio,
            matched_word_span=outcome.metrics.matched_word_span,
            matched_line_span=outcome.metrics.matched_line_span,
            near_overprint_composite_evidence=True,
            near_overprint_cleaned=False,
            near_overprint_ambiguous=True,
        )
        metrics, g, u, t, im = build_page_metrics(page, policy)
        bundle = decide_page_trust(
            page,
            metrics=metrics,
            geometry_m=g,
            unicode_m=u,
            text_m=t,
            image_m=im,
            policy=policy,
            source_type="pdf",
        )
        assert bundle.trust.decision is NativePageDecision.REJECTED
        assert bundle.trust.hard_rejection
        assert (
            NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value in bundle.trust.reason_codes
        )
        assert not bundle.accept_text


def test_soft_score_cannot_override_unpublished_composite() -> None:
    """Composite evidence with uncleaned doubles must hard-reject above 0.75 score."""

    policy = NativeTrustPolicyConfig()
    metrics = NearOverprintMetrics(
        strict_duplicate_ratio=0.0,
        near_overprint_duplicate_ratio=0.10,
        duplicate_layer_count=2,
        dominant_duplicate_offset_x=1.5,
        dominant_duplicate_offset_y=1.5,
        duplicate_layer_coverage_ratio=0.95,
        matched_near_duplicate_count=40,
        dominant_offset_support_ratio=0.9,
        matched_word_span=5,
        matched_line_span=3,
        composite_duplicate_layer_evidence=True,
    )
    assert composite_duplicate_layer_evidence(metrics, CompositeThresholds())

    # Leave doubled chars published (simulates v1.3 soft-only failure mode).
    doubled = _double_line("ABCDEFGHIJKLMNOPQRST")
    page = PageExtractionCandidate(
        page_number=1,
        page_width=612,
        page_height=792,
        page_bbox_x0=0,
        page_bbox_top=0,
        raw_character_count=len(doubled),
        characters=doubled,
        words=rebuild_words_from_characters(doubled),
        images=[],
        page_dimension_match=True,
        near_overprint_duplicate_ratio=0.10,
        duplicate_layer_coverage_ratio=0.95,
        matched_near_duplicate_count=40,
        dominant_offset_support_ratio=0.9,
        matched_word_span=5,
        matched_line_span=3,
        near_overprint_composite_evidence=True,
        near_overprint_cleaned=False,
        near_overprint_ambiguous=False,
    )
    m, g, u, t, im = build_page_metrics(page, policy)
    bundle = decide_page_trust(
        page,
        metrics=m,
        geometry_m=g,
        unicode_m=u,
        text_m=t,
        image_m=im,
        policy=policy,
        source_type="pdf",
    )
    assert bundle.trust.hard_rejection
    assert bundle.trust.decision is NativePageDecision.REJECTED
    assert NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value in bundle.trust.reason_codes
