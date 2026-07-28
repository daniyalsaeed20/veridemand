"""Native trust scoring and hard-rejection rules (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.contracts.canonical import CanonicalPageSourceType
from backend.app.contracts.native import (
    DuplicateLayerEvidence,
    NativePageDecision,
    NativePageMetrics,
    NativePageTrustResult,
    NativeTrustComponents,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.geometry_quality import GeometryMetrics
from backend.app.extraction.native.image_dominance import ImageDominanceMetrics
from backend.app.extraction.native.models import NativeTrustPolicyConfig, PageExtractionCandidate
from backend.app.extraction.native.near_overprint import (
    DEFAULT_GEOMETRIC_INTERLEAVE_RATIO,
    CompositeThresholds,
    NearOverprintMetrics,
    build_duplicate_layer_evidence,
    composite_duplicate_layer_evidence,
    geometric_interleave_ratio,
    max_consecutive_double_pair_run,
)
from backend.app.extraction.native.text_quality import TextStructureMetrics
from backend.app.extraction.native.unicode_quality import UnicodeMetrics

# Weights must sum to 1.0.
_WEIGHTS = {
    "character_validity_score": 0.25,
    "geometry_validity_score": 0.25,
    "duplication_quality_score": 0.15,
    "token_structure_score": 0.10,
    "text_density_score": 0.10,
    "order_plausibility_score": 0.05,
    "image_compatibility_score": 0.10,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 1e-9


@dataclass(frozen=True, slots=True)
class PageTrustDecisionBundle:
    trust: NativePageTrustResult
    geometry: GeometryMetrics
    accept_text: bool


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_components(
    unicode_m: UnicodeMetrics,
    geometry_m: GeometryMetrics,
    text_m: TextStructureMetrics,
    image_m: ImageDominanceMetrics,
    *,
    policy: NativeTrustPolicyConfig,
    near_overprint_ratio_for_score: float | None = None,
) -> NativeTrustComponents:
    char_validity = 1.0 - max(
        unicode_m.replacement_character_ratio / max(policy.native_max_replacement_ratio, 1e-9),
        unicode_m.control_character_ratio / max(policy.native_max_control_ratio, 1e-9),
        unicode_m.private_use_character_ratio / max(policy.native_max_private_use_ratio, 1e-9),
        unicode_m.unassigned_character_ratio / max(policy.native_max_unassigned_ratio, 1e-9),
        unicode_m.noncharacter_ratio,
        unicode_m.unprintable_character_ratio,
    )
    geometry_validity = 1.0 - max(
        geometry_m.invalid_geometry_ratio / max(policy.native_max_invalid_geometry_ratio, 1e-9),
        geometry_m.out_of_bounds_character_ratio / max(policy.native_max_out_of_bounds_ratio, 1e-9),
        geometry_m.zero_area_character_ratio,
        geometry_m.invalid_word_geometry_ratio,
    )
    near_ratio = (
        geometry_m.near_overprint_duplicate_ratio
        if near_overprint_ratio_for_score is None
        else near_overprint_ratio_for_score
    )
    duplication = 1.0 - max(
        geometry_m.duplicate_character_ratio / max(policy.native_max_duplicate_ratio, 1e-9),
        near_ratio / max(policy.native_max_near_overprint_ratio, 1e-9),
    )
    token = 1.0 - max(
        text_m.cid_token_ratio / max(policy.native_max_cid_token_ratio, 1e-9),
        text_m.symbol_only_word_ratio / max(policy.native_max_symbol_only_word_ratio, 1e-9),
        text_m.single_character_word_ratio
        / max(policy.native_max_single_character_word_ratio, 1e-9),
        text_m.very_long_token_ratio,
    )
    # Prefer moderate density; empty or extremely dense pages score lower.
    density = _clamp01(min(text_m.words_per_page_area * 5000.0, 1.0))
    if text_m.word_count == 0:
        density = 0.0
    order = 1.0 - text_m.extraction_order_backtrack_ratio
    image_compat = 0.0 if image_m.image_dominant else 1.0 - image_m.largest_image_area_ratio * 0.5

    return NativeTrustComponents(
        character_validity_score=_clamp01(char_validity),
        geometry_validity_score=_clamp01(geometry_validity),
        duplication_quality_score=_clamp01(duplication),
        token_structure_score=_clamp01(token),
        text_density_score=_clamp01(density),
        order_plausibility_score=_clamp01(order),
        image_compatibility_score=_clamp01(image_compat),
    )


def weighted_trust_score(components: NativeTrustComponents) -> float:
    data = components.model_dump()
    total = 0.0
    for name, weight in _WEIGHTS.items():
        total += float(data[name]) * weight
    return total


def decide_page_trust(
    page: PageExtractionCandidate,
    *,
    metrics: NativePageMetrics,
    geometry_m: GeometryMetrics,
    unicode_m: UnicodeMetrics,
    text_m: TextStructureMetrics,
    image_m: ImageDominanceMetrics,
    policy: NativeTrustPolicyConfig,
    source_type: str,
) -> PageTrustDecisionBundle:
    reasons: list[str] = []
    warnings: list[str] = [NativeReasonCode.VISUAL_AGREEMENT_NOT_EVALUATED_PHASE_3.value]
    hard = False
    duplicate_hard = False

    is_image_source = source_type == CanonicalPageSourceType.IMAGE.value

    if page.extraction_error:
        hard = True
        reasons.append(NativeReasonCode.NATIVE_EXTRACTION_ERROR.value)

    if is_image_source:
        hard = True
        reasons.append(NativeReasonCode.CANONICAL_IMAGE_SOURCE.value)

    if not page.page_dimension_match:
        hard = True
        reasons.append(NativeReasonCode.NATIVE_PAGE_METADATA_MISMATCH.value)

    meaningful_chars = [c for c in page.characters if not c.text.isspace()]
    sparse = (
        not page.characters
        or not page.words
        or len(meaningful_chars) < policy.native_min_characters
    )
    # Near-overprint ambiguity clears text intentionally; do not treat as mere absence.
    if sparse and not is_image_source and not page.near_overprint_ambiguous:
        reasons.append(NativeReasonCode.NATIVE_TEXT_ABSENT.value)
        if page.characters and len(meaningful_chars) < policy.native_min_characters:
            reasons.append(NativeReasonCode.NATIVE_TEXT_TOO_SPARSE.value)
        hard = True

    if page.near_overprint_ambiguous:
        hard = True
        duplicate_hard = True
        reasons.append(NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value)

    # Composite duplicate-layer hard rule — independent of weighted trust score.
    # Cleaned pages keep pre-clean diagnostics for UI but must not hard-reject.
    thr = CompositeThresholds(
        max_near_overprint_ratio=policy.native_max_near_overprint_ratio,
        max_duplicate_layer_coverage_ratio=policy.native_max_duplicate_layer_coverage_ratio,
        min_near_duplicate_match_count=policy.native_min_near_duplicate_match_count,
        min_dominant_offset_support_ratio=policy.native_min_dominant_offset_support_ratio,
        offset_cluster_abs_tol=policy.native_offset_cluster_abs_tol,
        offset_cluster_size_factor=policy.native_offset_cluster_size_factor,
        offset_cluster_top_k=policy.native_offset_cluster_top_k,
        path_b_min_coverage=policy.native_path_b_min_coverage,
        path_b_min_matches=policy.native_path_b_min_matches,
        path_b_min_duplicate_lines=policy.native_path_b_min_duplicate_lines,
        path_b_min_duplicate_regions=policy.native_path_b_min_duplicate_regions,
        region_min_chars=policy.native_region_min_chars,
        region_severe_ratio=policy.native_region_severe_ratio,
        region_min_matched=policy.native_region_min_matched,
    )
    composite_metrics = NearOverprintMetrics(
        strict_duplicate_ratio=geometry_m.strict_duplicate_ratio,
        near_overprint_duplicate_ratio=geometry_m.near_overprint_duplicate_ratio,
        duplicate_layer_count=geometry_m.duplicate_layer_count,
        dominant_duplicate_offset_x=geometry_m.dominant_duplicate_offset_x,
        dominant_duplicate_offset_y=geometry_m.dominant_duplicate_offset_y,
        duplicate_layer_coverage_ratio=geometry_m.duplicate_layer_coverage_ratio,
        matched_near_duplicate_count=geometry_m.matched_near_duplicate_count,
        dominant_offset_support_ratio=geometry_m.dominant_offset_support_ratio,
        matched_word_span=page.matched_word_span,
        matched_line_span=page.matched_line_span,
        composite_duplicate_layer_evidence=page.near_overprint_composite_evidence,
        top_offset_cluster_support_ratio=geometry_m.top_offset_cluster_support_ratio,
        top_k_offset_cluster_support_ratio=geometry_m.top_k_offset_cluster_support_ratio,
        offset_cluster_count=geometry_m.offset_cluster_count,
        duplicate_line_count=geometry_m.duplicate_line_count,
        duplicate_region_count=geometry_m.duplicate_region_count,
        page_vertical_span_ratio=geometry_m.page_vertical_span_ratio,
        page_horizontal_span_ratio=geometry_m.page_horizontal_span_ratio,
        hard_rule_path=geometry_m.hard_rule_path,
        hard_rule_explanation=geometry_m.hard_rule_explanation,
        duplicate_layer_evidence=geometry_m.duplicate_layer_evidence,
    )
    dup_evidence = (
        geometry_m.duplicate_layer_evidence
        if isinstance(geometry_m.duplicate_layer_evidence, DuplicateLayerEvidence)
        else build_duplicate_layer_evidence(composite_metrics, thr)
    )
    if not page.near_overprint_cleaned and (
        page.near_overprint_composite_evidence
        or composite_duplicate_layer_evidence(composite_metrics, thr)
    ):
        hard = True
        duplicate_hard = True
        reasons.append(NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value)

    # Output-level geometric interleave invariant (before accept).
    # Sparse bold/shadow / short header overprints must not force reject alone.
    if (
        page.characters
        and not page.near_overprint_ambiguous
        and page.matched_near_duplicate_count >= policy.native_min_near_duplicate_match_count
        and geometric_interleave_ratio(page.characters) >= DEFAULT_GEOMETRIC_INTERLEAVE_RATIO
    ):
        hard = True
        reasons.append(NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value)

    # Dense AABB runs (SSYYNN…) indicate residual overprint; ignore English doubles.
    if page.words and not page.near_overprint_ambiguous:
        provisional = " ".join(w.text for w in page.words)
        if max_consecutive_double_pair_run(provisional) >= 4:
            hard = True
            reasons.append(NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value)

    if len(page.characters) > policy.native_max_characters_per_page:
        hard = True
        reasons.append(NativeReasonCode.NATIVE_CHARACTER_LIMIT_EXCEEDED.value)
    if len(page.words) > policy.native_max_words_per_page:
        hard = True
        reasons.append(NativeReasonCode.NATIVE_WORD_LIMIT_EXCEEDED.value)

    ratio_checks = [
        (
            unicode_m.replacement_character_ratio,
            policy.native_max_replacement_ratio,
            NativeReasonCode.HIGH_REPLACEMENT_CHARACTER_RATIO,
        ),
        (
            unicode_m.control_character_ratio,
            policy.native_max_control_ratio,
            NativeReasonCode.HIGH_CONTROL_CHARACTER_RATIO,
        ),
        (
            unicode_m.private_use_character_ratio,
            policy.native_max_private_use_ratio,
            NativeReasonCode.HIGH_PRIVATE_USE_CHARACTER_RATIO,
        ),
        (
            unicode_m.unassigned_character_ratio,
            policy.native_max_unassigned_ratio,
            NativeReasonCode.HIGH_UNASSIGNED_CHARACTER_RATIO,
        ),
        (
            text_m.cid_token_ratio,
            policy.native_max_cid_token_ratio,
            NativeReasonCode.HIGH_CID_TOKEN_RATIO,
        ),
        (
            geometry_m.invalid_geometry_ratio,
            policy.native_max_invalid_geometry_ratio,
            NativeReasonCode.INVALID_CHARACTER_GEOMETRY,
        ),
        (
            geometry_m.out_of_bounds_character_ratio,
            policy.native_max_out_of_bounds_ratio,
            NativeReasonCode.TEXT_OUTSIDE_PAGE_BOUNDS,
        ),
        (
            geometry_m.duplicate_character_ratio,
            policy.native_max_duplicate_ratio,
            NativeReasonCode.EXCESSIVE_DUPLICATE_CHARACTERS,
        ),
        (
            text_m.symbol_only_word_ratio,
            policy.native_max_symbol_only_word_ratio,
            NativeReasonCode.HIGH_SYMBOL_ONLY_WORD_RATIO,
        ),
        (
            text_m.single_character_word_ratio,
            policy.native_max_single_character_word_ratio,
            NativeReasonCode.HIGH_SINGLE_CHARACTER_WORD_RATIO,
        ),
    ]
    for value, limit, reason in ratio_checks:
        if value > limit:
            hard = True
            reasons.append(reason.value)

    if unicode_m.noncharacter_ratio > policy.native_max_unassigned_ratio:
        hard = True
        reasons.append(NativeReasonCode.HIGH_NONCHARACTER_RATIO.value)
    if unicode_m.unprintable_character_ratio > policy.native_max_control_ratio:
        hard = True
        reasons.append(NativeReasonCode.HIGH_UNPRINTABLE_CHARACTER_RATIO.value)
    if geometry_m.zero_area_character_ratio > policy.native_max_invalid_geometry_ratio:
        hard = True
        reasons.append(NativeReasonCode.ZERO_AREA_TEXT_GEOMETRY.value)
    if geometry_m.invalid_word_geometry_ratio > policy.native_max_invalid_geometry_ratio:
        hard = True
        reasons.append(NativeReasonCode.INVALID_WORD_GEOMETRY.value)
    if text_m.extraction_order_backtrack_ratio > 0.5:
        hard = True
        reasons.append(NativeReasonCode.UNSTABLE_EXTRACTION_ORDER.value)
    if text_m.very_long_token_ratio > 0.25 and text_m.cid_token_ratio > 0.0:
        hard = True
        reasons.append(NativeReasonCode.IMPROBABLE_TOKEN_STRUCTURE.value)

    if image_m.image_dominant and not is_image_source:
        hard = True
        reasons.append(NativeReasonCode.IMAGE_DOMINANT_PAGE.value)

    near_for_score = (
        0.0 if page.near_overprint_cleaned else geometry_m.near_overprint_duplicate_ratio
    )
    components = compute_components(
        unicode_m,
        geometry_m,
        text_m,
        image_m,
        policy=policy,
        near_overprint_ratio_for_score=near_for_score,
    )
    score = weighted_trust_score(components)
    evidence_for_metrics = (
        dup_evidence if isinstance(dup_evidence, DuplicateLayerEvidence) else None
    )
    metrics_with = metrics.model_copy(
        update={
            "components": components,
            "duplicate_layer_evidence": evidence_for_metrics or metrics.duplicate_layer_evidence,
            "hard_rule_path": (
                evidence_for_metrics.selected_path
                if evidence_for_metrics is not None
                else metrics.hard_rule_path
            ),
        }
    )

    if score < policy.native_trust_threshold:
        hard = True
        reasons.append(NativeReasonCode.NATIVE_TRUST_SCORE_BELOW_THRESHOLD.value)

    # Deduplicate reasons while preserving order.
    seen: set[str] = set()
    ordered_reasons: list[str] = []
    for code in reasons:
        if code not in seen:
            seen.add(code)
            ordered_reasons.append(code)

    native_present = len(page.characters) > 0

    if is_image_source:
        decision = NativePageDecision.ABSENT
        source_mode = SourceMode.IMAGE_AUTHORITY
        accept = False
    elif page.extraction_error:
        decision = NativePageDecision.ERROR
        source_mode = SourceMode.VISUAL_AUTHORITY
        accept = False
    elif page.near_overprint_ambiguous:
        decision = NativePageDecision.REJECTED
        source_mode = SourceMode.VISUAL_AUTHORITY
        accept = False
        if NativeReasonCode.NATIVE_TEXT_REJECTED.value not in ordered_reasons:
            ordered_reasons.append(NativeReasonCode.NATIVE_TEXT_REJECTED.value)
    elif not native_present or (
        NativeReasonCode.NATIVE_TEXT_ABSENT.value in ordered_reasons
        and NativeReasonCode.NATIVE_TEXT_TOO_SPARSE.value not in ordered_reasons
        and len(page.characters) == 0
    ):
        decision = NativePageDecision.ABSENT
        source_mode = SourceMode.VISUAL_AUTHORITY
        accept = False
    elif hard:
        decision = NativePageDecision.REJECTED
        source_mode = SourceMode.VISUAL_AUTHORITY
        accept = False
        if NativeReasonCode.NATIVE_TEXT_REJECTED.value not in ordered_reasons:
            ordered_reasons.append(NativeReasonCode.NATIVE_TEXT_REJECTED.value)
    else:
        decision = NativePageDecision.ACCEPTED
        source_mode = SourceMode.NATIVE_AUTHORITY
        accept = True

    trust = NativePageTrustResult(
        page_number=page.page_number,
        decision=decision,
        source_mode=source_mode,
        native_text_present=native_present,
        native_trust_score=round(score, 6),
        trust_policy_version=policy.native_trust_policy_version,
        hard_rejection=hard and decision is not NativePageDecision.ACCEPTED,
        duplicate_hard_rejection=duplicate_hard and decision is not NativePageDecision.ACCEPTED,
        reason_codes=ordered_reasons,
        warning_codes=warnings,
        metrics=metrics_with,
        visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
        visual_agreement_score=None,
        native_result_available=accept,
        visual_processing_required=not accept,
    )
    return PageTrustDecisionBundle(trust=trust, geometry=geometry_m, accept_text=accept)
