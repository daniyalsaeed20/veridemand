"""Aggregate page-level native metrics."""

from __future__ import annotations

from backend.app.contracts.native import NativePageMetrics, NativeTrustComponents
from backend.app.extraction.native.geometry_quality import GeometryMetrics, analyse_geometry
from backend.app.extraction.native.image_dominance import (
    ImageDominanceMetrics,
    analyse_image_dominance,
)
from backend.app.extraction.native.models import NativeTrustPolicyConfig, PageExtractionCandidate
from backend.app.extraction.native.text_quality import TextStructureMetrics, analyse_text_structure
from backend.app.extraction.native.unicode_quality import UnicodeMetrics, analyse_unicode


def build_page_metrics(
    page: PageExtractionCandidate,
    policy: NativeTrustPolicyConfig,
    *,
    components: NativeTrustComponents | None = None,
) -> tuple[
    NativePageMetrics, GeometryMetrics, UnicodeMetrics, TextStructureMetrics, ImageDominanceMetrics
]:
    unicode_m = analyse_unicode(page.characters)
    geometry_m = analyse_geometry(
        page, coordinate_tolerance_points=policy.native_coordinate_tolerance_points
    )
    text_m = analyse_text_structure(
        page.characters,
        page.words,
        page_width=page.page_width,
        page_height=page.page_height,
    )
    image_m = analyse_image_dominance(
        page.images,
        page_width=page.page_width,
        page_height=page.page_height,
        page_bbox_x0=page.page_bbox_x0,
        page_bbox_top=page.page_bbox_top,
        dominant_ratio=policy.native_image_dominant_area_ratio,
    )
    metrics = NativePageMetrics(
        raw_character_count=geometry_m.raw_character_count,
        deduplicated_character_count=geometry_m.deduplicated_character_count,
        word_count=text_m.word_count,
        character_count=text_m.character_count,
        duplicate_character_ratio=geometry_m.duplicate_character_ratio,
        strict_duplicate_ratio=geometry_m.strict_duplicate_ratio,
        near_overprint_duplicate_ratio=geometry_m.near_overprint_duplicate_ratio,
        duplicate_layer_count=geometry_m.duplicate_layer_count,
        dominant_duplicate_offset_x=geometry_m.dominant_duplicate_offset_x,
        dominant_duplicate_offset_y=geometry_m.dominant_duplicate_offset_y,
        duplicate_layer_coverage_ratio=geometry_m.duplicate_layer_coverage_ratio,
        matched_near_duplicate_count=geometry_m.matched_near_duplicate_count,
        dominant_offset_support_ratio=geometry_m.dominant_offset_support_ratio,
        matched_word_span=geometry_m.matched_word_span,
        matched_line_span=geometry_m.matched_line_span,
        top_offset_cluster_support_ratio=geometry_m.top_offset_cluster_support_ratio,
        top_k_offset_cluster_support_ratio=geometry_m.top_k_offset_cluster_support_ratio,
        offset_cluster_count=geometry_m.offset_cluster_count,
        duplicate_line_count=geometry_m.duplicate_line_count,
        duplicate_region_count=geometry_m.duplicate_region_count,
        page_vertical_span_ratio=geometry_m.page_vertical_span_ratio,
        page_horizontal_span_ratio=geometry_m.page_horizontal_span_ratio,
        hard_rule_path=geometry_m.hard_rule_path,
        hard_rule_explanation=list(geometry_m.hard_rule_explanation),
        replacement_character_ratio=unicode_m.replacement_character_ratio,
        control_character_ratio=unicode_m.control_character_ratio,
        private_use_character_ratio=unicode_m.private_use_character_ratio,
        unassigned_character_ratio=unicode_m.unassigned_character_ratio,
        noncharacter_ratio=unicode_m.noncharacter_ratio,
        unprintable_character_ratio=unicode_m.unprintable_character_ratio,
        cid_token_ratio=text_m.cid_token_ratio,
        invalid_geometry_ratio=geometry_m.invalid_geometry_ratio,
        out_of_bounds_character_ratio=geometry_m.out_of_bounds_character_ratio,
        zero_area_character_ratio=geometry_m.zero_area_character_ratio,
        invalid_word_geometry_ratio=geometry_m.invalid_word_geometry_ratio,
        single_character_word_ratio=text_m.single_character_word_ratio,
        symbol_only_word_ratio=text_m.symbol_only_word_ratio,
        alphanumeric_word_ratio=text_m.alphanumeric_word_ratio,
        very_long_token_ratio=text_m.very_long_token_ratio,
        repeated_token_ratio=text_m.repeated_token_ratio,
        whitespace_ratio=unicode_m.whitespace_ratio,
        font_count=text_m.font_count,
        missing_font_ratio=text_m.missing_font_ratio,
        upright_character_ratio=text_m.upright_character_ratio,
        extraction_order_backtrack_ratio=text_m.extraction_order_backtrack_ratio,
        characters_per_page_area=text_m.characters_per_page_area,
        words_per_page_area=text_m.words_per_page_area,
        image_count=image_m.image_count,
        largest_image_area_ratio=image_m.largest_image_area_ratio,
        total_clipped_image_area_ratio=image_m.total_clipped_image_area_ratio,
        page_dimension_match=geometry_m.page_dimension_match,
        components=components,
    )
    return metrics, geometry_m, unicode_m, text_m, image_m
