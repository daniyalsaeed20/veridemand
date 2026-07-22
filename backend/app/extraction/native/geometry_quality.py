"""Geometry quality metrics for native candidates."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.contracts.native import PdfPointBox
from backend.app.extraction.native.coordinates import (
    MappedBox,
    map_pdfplumber_box,
    word_contains_characters,
)
from backend.app.extraction.native.models import (
    PageExtractionCandidate,
    RawCharCandidate,
    RawWordCandidate,
)


@dataclass(slots=True)
class CharGeomResult:
    mapped: MappedBox
    candidate: RawCharCandidate


@dataclass(slots=True)
class WordGeomResult:
    mapped: MappedBox
    candidate: RawWordCandidate
    contains_chars: bool


@dataclass(frozen=True, slots=True)
class GeometryMetrics:
    raw_character_count: int
    deduplicated_character_count: int
    duplicate_character_ratio: float
    strict_duplicate_ratio: float
    near_overprint_duplicate_ratio: float
    duplicate_layer_count: int
    dominant_duplicate_offset_x: float
    dominant_duplicate_offset_y: float
    duplicate_layer_coverage_ratio: float
    matched_near_duplicate_count: int
    dominant_offset_support_ratio: float
    matched_word_span: int
    matched_line_span: int
    top_offset_cluster_support_ratio: float
    top_k_offset_cluster_support_ratio: float
    offset_cluster_count: int
    duplicate_line_count: int
    duplicate_region_count: int
    page_vertical_span_ratio: float
    page_horizontal_span_ratio: float
    hard_rule_path: str
    hard_rule_explanation: tuple[str, ...]
    zero_area_character_ratio: float
    invalid_geometry_ratio: float
    out_of_bounds_character_ratio: float
    invalid_word_geometry_ratio: float
    page_dimension_match: bool
    char_results: list[CharGeomResult]
    word_results: list[WordGeomResult]


def analyse_geometry(
    page: PageExtractionCandidate,
    *,
    coordinate_tolerance_points: float,
) -> GeometryMetrics:
    """Map candidates and compute geometry quality ratios."""

    raw = page.raw_character_count
    deduped = len(page.characters)
    # Strict ratio is owned by the extractor (pdfplumber dedupe only).
    # Do not recompute from post-clean counts — near-overprint cleaning is separate.
    strict_ratio = max(0.0, min(1.0, page.strict_duplicate_ratio))
    duplicate_ratio = strict_ratio

    char_results: list[CharGeomResult] = []
    zero_area = 0
    invalid = 0
    oob = 0
    for cand in page.characters:
        mapped = map_pdfplumber_box(
            x0=cand.x0,
            x1=cand.x1,
            top=cand.top,
            bottom=cand.bottom,
            page_bbox_x0=page.page_bbox_x0,
            page_bbox_top=page.page_bbox_top,
            page_width=page.page_width,
            page_height=page.page_height,
            coordinate_tolerance_points=coordinate_tolerance_points,
        )
        if mapped.zero_area:
            zero_area += 1
        if mapped.invalid:
            invalid += 1
        if mapped.out_of_bounds:
            oob += 1
        char_results.append(CharGeomResult(mapped=mapped, candidate=cand))

    word_results: list[WordGeomResult] = []
    invalid_words = 0
    for word in page.words:
        mapped = map_pdfplumber_box(
            x0=word.x0,
            x1=word.x1,
            top=word.top,
            bottom=word.bottom,
            page_bbox_x0=page.page_bbox_x0,
            page_bbox_top=page.page_bbox_top,
            page_width=page.page_width,
            page_height=page.page_height,
            coordinate_tolerance_points=coordinate_tolerance_points,
        )
        linked_boxes: list[PdfPointBox] = []
        for idx in word.char_indices:
            if 0 <= idx < len(char_results) and not char_results[idx].mapped.invalid:
                linked_boxes.append(char_results[idx].mapped.pdf_point_bbox)
        contains = True
        if linked_boxes and not mapped.invalid:
            contains = word_contains_characters(
                mapped.pdf_point_bbox,
                linked_boxes,
                tolerance_points=coordinate_tolerance_points,
            )
        if mapped.invalid or mapped.out_of_bounds or not contains:
            invalid_words += 1
        word_results.append(WordGeomResult(mapped=mapped, candidate=word, contains_chars=contains))

    denom = max(len(page.characters), 1)
    word_denom = max(len(page.words), 1)
    return GeometryMetrics(
        raw_character_count=raw,
        deduplicated_character_count=deduped,
        duplicate_character_ratio=max(0.0, min(1.0, duplicate_ratio)),
        strict_duplicate_ratio=max(0.0, min(1.0, strict_ratio)),
        near_overprint_duplicate_ratio=max(0.0, min(1.0, page.near_overprint_duplicate_ratio)),
        duplicate_layer_count=max(1, page.duplicate_layer_count),
        dominant_duplicate_offset_x=page.dominant_duplicate_offset_x,
        dominant_duplicate_offset_y=page.dominant_duplicate_offset_y,
        duplicate_layer_coverage_ratio=max(0.0, min(1.0, page.duplicate_layer_coverage_ratio)),
        matched_near_duplicate_count=max(0, page.matched_near_duplicate_count),
        dominant_offset_support_ratio=max(0.0, min(1.0, page.dominant_offset_support_ratio)),
        matched_word_span=max(0, page.matched_word_span),
        matched_line_span=max(0, page.matched_line_span),
        top_offset_cluster_support_ratio=max(0.0, min(1.0, page.top_offset_cluster_support_ratio)),
        top_k_offset_cluster_support_ratio=max(
            0.0, min(1.0, page.top_k_offset_cluster_support_ratio)
        ),
        offset_cluster_count=max(0, page.offset_cluster_count),
        duplicate_line_count=max(0, page.duplicate_line_count),
        duplicate_region_count=max(0, page.duplicate_region_count),
        page_vertical_span_ratio=max(0.0, min(1.0, page.page_vertical_span_ratio)),
        page_horizontal_span_ratio=max(0.0, min(1.0, page.page_horizontal_span_ratio)),
        hard_rule_path=page.hard_rule_path or "none",
        hard_rule_explanation=tuple(page.hard_rule_explanation or ()),
        zero_area_character_ratio=zero_area / denom,
        invalid_geometry_ratio=invalid / denom,
        out_of_bounds_character_ratio=oob / denom,
        invalid_word_geometry_ratio=invalid_words / word_denom,
        page_dimension_match=page.page_dimension_match,
        char_results=char_results,
        word_results=word_results,
    )
