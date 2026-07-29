"""Correction 5 unit tests: printed OCR quality gate and pass selection."""

from __future__ import annotations

from types import SimpleNamespace

from PIL import Image, ImageDraw

from backend.app.contracts.ocr import (
    OcrPassKind,
    OcrQualityStatus,
    PageProcessingProfile,
    ProvisionalItemClass,
)
from backend.app.extraction.visual.noise import classify_raw_item, classify_raw_lines
from backend.app.extraction.visual.page_profile import PageProfileResult, analyse_page_profile
from backend.app.extraction.visual.quality import (
    apply_primary_quality_gate,
    build_quality_evidence,
    compare_ocr_passes,
    thresholds_for_profile,
)


def _raw(text: str, score: float, x0: float, y0: float, x1: float, y1: float) -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        recognition_score=score,
        detection_score=score,
        polygon_px=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)],
        words=[],
    )


def _ordinary_profile() -> PageProfileResult:
    return PageProfileResult(
        page_profile=PageProcessingProfile.ORDINARY_DOCUMENT,
        profile_confidence=0.5,
        profile_reason_codes=["ordinary_structure"],
        horizontal_line_density=0.01,
        vertical_line_density=0.01,
        grid_intersection_count=0,
        small_component_density=0.0,
        checkbox_like_count=0,
        median_box_area_ratio=0.01,
        text_region_density=0.05,
        page_edge_density=0.05,
    )


def _dense_profile() -> PageProfileResult:
    return PageProfileResult(
        page_profile=PageProcessingProfile.DENSE_FORM,
        profile_confidence=0.8,
        profile_reason_codes=["long_horizontal_rules", "long_vertical_rules"],
        horizontal_line_density=0.08,
        vertical_line_density=0.06,
        grid_intersection_count=20,
        small_component_density=0.2,
        checkbox_like_count=12,
        median_box_area_ratio=0.0004,
        text_region_density=0.2,
        page_edge_density=0.1,
    )


def test_clean_page_primary_pass_accepted() -> None:
    lines = [
        _raw("Dear Sir or Madam", 0.95, 40, 40, 400, 60),
        _raw("This is a clean typed letter about coverage.", 0.93, 40, 80, 500, 100),
        _raw("Please contact us at your earliest convenience.", 0.94, 40, 120, 520, 140),
    ]
    evidence = build_quality_evidence(
        lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=600,
        page_height=800,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_ordinary_profile(),
        grid=None,
    )
    assert evidence.quality_gate_passed is True
    assert evidence.fallback_recommended is False
    assert evidence.quality_status in {OcrQualityStatus.GOOD, OcrQualityStatus.USABLE_WITH_WARNINGS}


def test_dense_form_profile_selected_from_ruled_image() -> None:
    img = Image.new("RGB", (400, 500), "white")
    draw = ImageDraw.Draw(img)
    for y in range(20, 480, 12):
        draw.line([(10, y), (390, y)], fill="black", width=1)
    for x in range(20, 380, 40):
        draw.line([(x, 10), (x, 490)], fill="black", width=1)
    result = analyse_page_profile(img, raw_lines=[])
    assert result.page_profile is PageProcessingProfile.DENSE_FORM
    assert result.profile_confidence > 0.5


def test_fragmented_primary_triggers_fallback() -> None:
    # Many single-character tokens → high fragmentation on dense form.
    lines = [
        _raw(ch, 0.8, 10 + i * 8, 20 + (i % 40) * 10, 14 + i * 8, 28 + (i % 40) * 10)
        for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" * 4)
    ]
    evidence = build_quality_evidence(
        lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=800,
        page_height=1000,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_dense_profile(),
        grid=None,
    )
    assert evidence.quality_gate_passed is False
    assert evidence.fallback_recommended is True
    assert evidence.fragmentation_score > 0.4


def test_low_confidence_ratio_can_trigger_fallback() -> None:
    lines = [_raw(f"word{i}", 0.4, 10, 10 + i * 20, 80, 25 + i * 20) for i in range(20)]
    evidence = build_quality_evidence(
        lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=400,
        page_height=600,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_ordinary_profile(),
        grid=None,
    )
    assert evidence.fallback_recommended is True
    assert "high_low_confidence_ratio" in evidence.fallback_reason_codes


def test_symbol_only_ratio_can_trigger_fallback() -> None:
    lines = [_raw("|", 0.9, 10, 10 + i * 5, 12, 40 + i * 5) for i in range(30)]
    lines += [_raw("Name", 0.9, 50, 50, 100, 70)]
    evidence = build_quality_evidence(
        lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=400,
        page_height=600,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_dense_profile(),
        grid=None,
    )
    assert evidence.fallback_recommended is True
    assert any(
        code in evidence.fallback_reason_codes
        for code in (
            "excessive_symbol_only_tokens",
            "excessive_fragmentation",
            "dense_form_fragmentation",
        )
    )


def test_page_confidence_alone_cannot_approve_poor_result() -> None:
    # High mean confidence but extreme fragmentation on dense form.
    lines = [
        _raw(ch, 0.95, 10 + i * 6, 20 + (i % 50) * 8, 14 + i * 6, 26 + (i % 50) * 8)
        for i, ch in enumerate("abcdefghijklmnopqrstuvwxyz0123456789" * 5)
    ]
    evidence = build_quality_evidence(
        lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=900,
        page_height=1100,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_dense_profile(),
        grid=None,
    )
    assert evidence.mean_confidence is not None and evidence.mean_confidence > 0.9
    assert evidence.quality_gate_passed is False


def test_sparse_page_not_rejected_for_sparsity() -> None:
    sparse_profile = PageProfileResult(
        page_profile=PageProcessingProfile.SPARSE_DOCUMENT,
        profile_confidence=0.7,
        profile_reason_codes=["sparse_text_coverage"],
        horizontal_line_density=0.0,
        vertical_line_density=0.0,
        grid_intersection_count=0,
        small_component_density=0.0,
        checkbox_like_count=0,
        median_box_area_ratio=0.02,
        text_region_density=0.005,
        page_edge_density=0.02,
    )
    lines = [_raw("Note: follow up tomorrow.", 0.92, 40, 40, 300, 60)]
    evidence = build_quality_evidence(
        lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=600,
        page_height=800,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=sparse_profile,
        grid=None,
    )
    assert evidence.quality_gate_passed is True
    assert "inadequate_text_coverage" not in evidence.fallback_reason_codes


def test_fallback_selected_when_measurably_better() -> None:
    primary_lines = [
        _raw(ch, 0.8, 10 + i * 8, 20, 14 + i * 8, 30)
        for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    ]
    primary = build_quality_evidence(
        primary_lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=600,
        page_height=400,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_dense_profile(),
        grid=None,
    )
    fallback_lines = [
        _raw("Patient Name Field Label", 0.92, 20, 20, 280, 40),
        _raw("Date of Incident 01/02/2024", 0.91, 20, 50, 300, 70),
        _raw("Officer Badge Number 4421", 0.90, 20, 80, 290, 100),
    ]
    fallback = build_quality_evidence(
        fallback_lines,
        page_number=1,
        ocr_pass=OcrPassKind.FALLBACK,
        detector_limit_side=1600,
        page_width=600,
        page_height=400,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_dense_profile(),
        grid=None,
    )
    comparison = compare_ocr_passes(
        primary,
        fallback,
        primary_valid_words=26,
        fallback_valid_words=12,
    )
    assert comparison.selected_pass is OcrPassKind.FALLBACK
    assert "fallback_measured_quality_improvement" in comparison.selection_reason_codes


def test_primary_retained_when_fallback_worse() -> None:
    primary_lines = [
        _raw("Clean heading text here", 0.9, 20, 20, 300, 40),
        _raw("Second line of content", 0.88, 20, 50, 280, 70),
    ]
    primary = build_quality_evidence(
        primary_lines,
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=600,
        page_height=400,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_ordinary_profile(),
        grid=None,
    )
    fallback_lines = [
        _raw(ch, 0.5, 10 + i * 5, 10 + i, 12 + i * 5, 14 + i)
        for i, ch in enumerate("abcdefghij" * 8)
    ]
    fallback = build_quality_evidence(
        fallback_lines,
        page_number=1,
        ocr_pass=OcrPassKind.FALLBACK,
        detector_limit_side=1600,
        page_width=600,
        page_height=400,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_ordinary_profile(),
        grid=None,
    )
    comparison = compare_ocr_passes(
        primary,
        fallback,
        primary_valid_words=8,
        fallback_valid_words=80,
    )
    assert comparison.selected_pass is OcrPassKind.PRIMARY
    assert any(
        code in comparison.selection_reason_codes
        for code in (
            "fallback_no_measured_improvement",
            "fallback_worse_fragmentation",
            "primary_retained",
        )
    )


def test_result_selection_deterministic() -> None:
    primary = build_quality_evidence(
        [_raw("Hello world", 0.9, 10, 10, 100, 30)],
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=200,
        page_height=200,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_ordinary_profile(),
        grid=None,
    )
    a = compare_ocr_passes(primary, None, primary_valid_words=2, fallback_valid_words=0)
    b = compare_ocr_passes(primary, None, primary_valid_words=2, fallback_valid_words=0)
    assert a.selected_pass == b.selected_pass
    assert a.selection_reason_codes == b.selection_reason_codes


def test_handwriting_remains_pending_phase_5() -> None:
    item = classify_raw_item(
        _raw("scrawl", 0.3, 10, 10, 40, 40),
        low_confidence_threshold=0.75,
        page_has_dense_form=True,
    )
    assert item.provisional_class is ProvisionalItemClass.HANDWRITING_CANDIDATE_PENDING_PHASE_5
    assert item.publish_in_transcript is False


def test_symbol_separated_from_transcript() -> None:
    classified = classify_raw_lines(
        [_raw("☐", 0.9, 10, 10, 20, 20), _raw("Printed Label", 0.95, 40, 10, 140, 30)],
        low_confidence_threshold=0.75,
        line_only_indices=set(),
        page_has_dense_form=True,
    )
    assert classified[0].provisional_class is ProvisionalItemClass.CHECKBOX_OR_SYMBOL_CANDIDATE
    assert classified[0].publish_in_transcript is False
    assert classified[1].publish_in_transcript is True


def test_dense_form_thresholds_stricter_than_ordinary() -> None:
    dense = thresholds_for_profile(PageProcessingProfile.DENSE_FORM)
    ordinary = thresholds_for_profile(PageProcessingProfile.ORDINARY_DOCUMENT)
    assert dense.max_fragmentation <= ordinary.max_fragmentation
    assert dense.max_single_char_token_ratio <= ordinary.max_single_char_token_ratio


def test_apply_gate_empty_page_does_not_force_fallback() -> None:
    empty = build_quality_evidence(
        [],
        page_number=1,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=960,
        page_width=100,
        page_height=100,
        low_confidence_threshold=0.75,
        preprocessing_variant=None,
        profile=_ordinary_profile(),
        grid=None,
    )
    gated = apply_primary_quality_gate(empty)
    assert gated.quality_gate_passed is True
    assert gated.fallback_recommended is False
