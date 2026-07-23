"""Unit tests for native visibility probe."""

from __future__ import annotations

from PIL import Image

from backend.app.contracts.geometry import Geometry, NormalisedBoundingBox, NormalisedPolygon
from backend.app.contracts.native import (
    NativePageDecision,
    NativePageMetrics,
    NativePageResult,
    NativePageTrustResult,
    NativeWord,
    PdfPointBox,
    RecognitionMethod,
    RecognitionStatus,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.visual import NativeVisibilityDecision
from backend.app.extraction.visual.visibility import VisibilityThresholds, probe_native_visibility


def _metrics() -> NativePageMetrics:
    return NativePageMetrics(
        raw_character_count=10,
        deduplicated_character_count=10,
        word_count=3,
        character_count=10,
        duplicate_character_ratio=0.0,
        replacement_character_ratio=0.0,
        control_character_ratio=0.0,
        private_use_character_ratio=0.0,
        unassigned_character_ratio=0.0,
        noncharacter_ratio=0.0,
        unprintable_character_ratio=0.0,
        cid_token_ratio=0.0,
        invalid_geometry_ratio=0.0,
        out_of_bounds_character_ratio=0.0,
        zero_area_character_ratio=0.0,
        invalid_word_geometry_ratio=0.0,
        single_character_word_ratio=0.0,
        symbol_only_word_ratio=0.0,
        alphanumeric_word_ratio=1.0,
        very_long_token_ratio=0.0,
        repeated_token_ratio=0.0,
        whitespace_ratio=0.0,
        font_count=1,
        missing_font_ratio=0.0,
        upright_character_ratio=1.0,
        extraction_order_backtrack_ratio=0.0,
        characters_per_page_area=0.01,
        words_per_page_area=0.001,
        image_count=0,
        largest_image_area_ratio=0.0,
        total_clipped_image_area_ratio=0.0,
        page_dimension_match=True,
    )


def _word(
    index: int, text: str, *, x: float, y: float, w: float = 0.2, h: float = 0.1
) -> NativeWord:
    bbox = NormalisedBoundingBox(x=x, y=y, width=w, height=h)
    polygon = NormalisedPolygon(
        points=[
            {"x": x, "y": y},
            {"x": x + w, "y": y},
            {"x": x + w, "y": y + h},
            {"x": x, "y": y + h},
        ],
    )
    return NativeWord(
        id=f"word_p0001_{index:06d}",
        page_number=1,
        sequence_index=index,
        text=text,
        normalised_text=text,
        character_ids=[],
        geometry=Geometry(bbox=bbox, polygon=polygon),
        pdf_point_bbox=PdfPointBox(x=x * 612, y=y * 792, width=w * 612, height=h * 792),
        upright=True,
        recognition_method=RecognitionMethod.NATIVE_PDF,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        recognition_status=RecognitionStatus.ACCEPTED,
    )


def _page(words: list[NativeWord]) -> NativePageResult:
    trust = NativePageTrustResult(
        page_number=1,
        decision=NativePageDecision.ACCEPTED,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        native_text_present=True,
        native_trust_score=0.9,
        trust_policy_version="phase3-v1",
        hard_rejection=False,
        reason_codes=[],
        warning_codes=[],
        metrics=_metrics(),
        visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
        visual_agreement_score=None,
        native_result_available=True,
        visual_processing_required=False,
    )
    return NativePageResult(
        page_number=1,
        decision=NativePageDecision.ACCEPTED,
        source_mode=SourceMode.NATIVE_AUTHORITY,
        trust=trust,
        words=words,
        characters=[],
        provisional_native_text=" ".join(w.text for w in words) or None,
    )


def test_insufficient_words_skips_downgrade() -> None:
    image = Image.new("RGB", (200, 200), (255, 255, 255))
    result = probe_native_visibility(
        image,
        _page([_word(0, "Hi", x=0.1, y=0.1)]),
        thresholds=VisibilityThresholds(
            min_words=3,
            min_visible_word_ratio=0.6,
            min_region_variance=20.0,
            min_edge_density=0.02,
        ),
    )
    assert result.native_visibility_decision is NativeVisibilityDecision.INSUFFICIENT_WORDS
    assert result.downgraded is False


def test_blank_page_downgrades_native() -> None:
    image = Image.new("RGB", (200, 200), (255, 255, 255))
    words = [
        _word(0, "One", x=0.1, y=0.1),
        _word(1, "Two", x=0.4, y=0.1),
        _word(2, "Three", x=0.1, y=0.4),
    ]
    result = probe_native_visibility(
        image,
        _page(words),
        thresholds=VisibilityThresholds(
            min_words=3,
            min_visible_word_ratio=0.6,
            min_region_variance=20.0,
            min_edge_density=0.02,
        ),
    )
    assert result.downgraded is True
    assert result.native_visibility_decision in {
        NativeVisibilityDecision.NATIVE_TEXT_NOT_VISUALLY_PRESENT,
        NativeVisibilityDecision.NATIVE_TEXT_VISIBILITY_UNCERTAIN,
    }


def test_unsampleable_words_downgrade_when_count_meets_min() -> None:
    image = Image.new("RGB", (200, 200), (255, 255, 255))
    # Tiny boxes that fail the 2px sample gate.
    words = [_word(i, f"W{i}", x=0.01 * i, y=0.01, w=0.001, h=0.001) for i in range(8)]
    result = probe_native_visibility(
        image,
        _page(words),
        thresholds=VisibilityThresholds(
            min_words=3,
            min_visible_word_ratio=0.6,
            min_region_variance=20.0,
            min_edge_density=0.02,
        ),
    )
    assert result.downgraded is True
    assert (
        result.native_visibility_decision
        is NativeVisibilityDecision.NATIVE_TEXT_VISIBILITY_UNCERTAIN
    )


def test_high_contrast_ink_supports_native() -> None:
    image = Image.new("RGB", (200, 200), (255, 255, 255))
    for x0, y0, x1, y1 in ((20, 20, 60, 40), (80, 20, 120, 40), (20, 80, 60, 100)):
        for x in range(x0, x1):
            for y in range(y0, y1):
                image.putpixel((x, y), (0, 0, 0))
    words = [
        _word(0, "One", x=0.1, y=0.1, w=0.2, h=0.1),
        _word(1, "Two", x=0.4, y=0.1, w=0.2, h=0.1),
        _word(2, "Three", x=0.1, y=0.4, w=0.2, h=0.1),
    ]
    result = probe_native_visibility(
        image,
        _page(words),
        thresholds=VisibilityThresholds(
            min_words=3,
            min_visible_word_ratio=0.6,
            min_region_variance=10.0,
            min_edge_density=0.01,
        ),
    )
    assert result.downgraded is False
    assert (
        result.native_visibility_decision is NativeVisibilityDecision.NATIVE_TEXT_VISUALLY_SUPPORTED
    )
