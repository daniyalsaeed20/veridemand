"""Correction 2: duplicate-layer evidence invariants and Path B structure."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.contracts.native import (
    DuplicateLayerEvidence,
    DuplicateRuleRecord,
    NativePageDecision,
    NativePageMetrics,
    NativePageResult,
    NativePageTrustResult,
    NativeTrustComponents,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.document_policy import (
    apply_document_escalation,
    decide_document_policy,
)
from backend.app.extraction.native.models import NativeTrustPolicyConfig
from backend.app.extraction.native.near_overprint import (
    CompositeThresholds,
    NearOverprintMetrics,
    build_duplicate_layer_evidence,
    path_a_widespread_duplication,
    path_b_coherent_partial_layer,
)
from backend.app.extraction.native.serializer import as_verification_words
from backend.app.extraction.routing.digital_native import (
    is_recoverable_escalation_suppressed,
    is_trusted_digital_native,
    restore_escalation_suppressed_native,
)


def _base_metrics(**overrides: object) -> NearOverprintMetrics:
    data: dict[str, object] = {
        "strict_duplicate_ratio": 0.0,
        "near_overprint_duplicate_ratio": 0.0,
        "duplicate_layer_count": 2,
        "dominant_duplicate_offset_x": 0.75,
        "dominant_duplicate_offset_y": 1.0,
        "duplicate_layer_coverage_ratio": 0.0,
        "matched_near_duplicate_count": 0,
        "dominant_offset_support_ratio": 0.1,
        "matched_word_span": 0,
        "matched_line_span": 0,
        "duplicate_line_count": 0,
        "duplicate_region_count": 0,
        "page_vertical_span_ratio": 0.0,
        "page_horizontal_span_ratio": 0.0,
        "offset_cluster_count": 1,
        "top_k_offset_cluster_support_ratio": 0.2,
    }
    data.update(overrides)
    return NearOverprintMetrics(**data)  # type: ignore[arg-type]


def test_path_b_rejects_sparse_22_matches_zero_lines_regions() -> None:
    """Billing-style false positive: 22 matches without structure must not select Path B."""

    metrics = _base_metrics(
        near_overprint_duplicate_ratio=0.0022,
        duplicate_layer_coverage_ratio=1.0,
        matched_near_duplicate_count=22,
        matched_word_span=4,
        matched_line_span=1,
        duplicate_line_count=0,
        duplicate_region_count=0,
        page_vertical_span_ratio=0.2,
    )
    thr = CompositeThresholds()
    evidence = build_duplicate_layer_evidence(metrics, thr)
    assert not evidence.path_b_satisfied
    assert evidence.selected_path == "none"
    assert not evidence.hard_rejection
    assert not path_b_coherent_partial_layer(metrics, thr)
    # Mandatory Path B structure rule fails; explanation cannot claim Path B.
    structure = next(r for r in evidence.path_b_rules if r.rule_id == "path_b_structure")
    assert structure.mandatory and not structure.passed


def test_path_a_fires_on_widespread_metrics() -> None:
    metrics = _base_metrics(
        near_overprint_duplicate_ratio=0.327,
        duplicate_layer_coverage_ratio=1.0,
        matched_near_duplicate_count=150,
        matched_word_span=12,
        matched_line_span=8,
        duplicate_line_count=8,
        duplicate_region_count=2,
        page_vertical_span_ratio=0.4,
    )
    thr = CompositeThresholds()
    evidence = build_duplicate_layer_evidence(metrics, thr)
    assert evidence.path_a_satisfied
    assert evidence.selected_path == "A"
    assert evidence.hard_rejection
    assert path_a_widespread_duplication(metrics, thr)


def test_path_b_fires_with_structure_and_diluted_ratio() -> None:
    metrics = _base_metrics(
        near_overprint_duplicate_ratio=0.058,
        duplicate_layer_coverage_ratio=1.0,
        matched_near_duplicate_count=335,
        matched_word_span=40,
        matched_line_span=14,
        duplicate_line_count=14,
        duplicate_region_count=3,
        page_vertical_span_ratio=0.55,
    )
    thr = CompositeThresholds()
    evidence = build_duplicate_layer_evidence(metrics, thr)
    assert not evidence.path_a_satisfied  # diluted near-ratio
    assert evidence.path_b_satisfied
    assert evidence.selected_path == "B"
    assert evidence.hard_rejection


def test_evidence_cannot_select_path_b_with_failed_mandatory_rule() -> None:
    with pytest.raises(ValidationError):
        DuplicateLayerEvidence(
            policy_version="phase3-v1.6",
            strict_duplicate_ratio=0.0,
            near_overprint_duplicate_ratio=0.0,
            duplicate_layer_coverage_ratio=1.0,
            matched_near_duplicate_count=22,
            duplicate_line_count=0,
            duplicate_region_count=0,
            path_a_rules=[],
            path_b_rules=[
                DuplicateRuleRecord(
                    rule_id="path_b_structure",
                    metric_name="duplicate_line_or_region_count",
                    actual_value="0",
                    operator="satisfies",
                    threshold="lines>=2",
                    mandatory=True,
                    passed=False,
                    applies_to_path="B",
                )
            ],
            path_a_satisfied=False,
            path_b_satisfied=True,
            selected_path="B",
            hard_rejection=True,
        )


def test_informational_rule_does_not_block_path_success() -> None:
    metrics = _base_metrics(
        near_overprint_duplicate_ratio=0.058,
        duplicate_layer_coverage_ratio=1.0,
        matched_near_duplicate_count=335,
        duplicate_line_count=14,
        duplicate_region_count=3,
        matched_word_span=40,
        matched_line_span=14,
        dominant_offset_support_ratio=0.01,
    )
    evidence = build_duplicate_layer_evidence(metrics, CompositeThresholds())
    info = [r for r in evidence.path_b_rules if not r.mandatory]
    assert info
    assert evidence.path_b_satisfied


def test_clean_metrics_do_not_trigger_duplicate_rejection() -> None:
    evidence = build_duplicate_layer_evidence(_base_metrics(), CompositeThresholds())
    assert evidence.selected_path == "none"
    assert not evidence.hard_rejection


def _empty_metrics() -> NativePageMetrics:
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
        whitespace_ratio=0.1,
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
        components=NativeTrustComponents(
            character_validity_score=1.0,
            geometry_validity_score=1.0,
            duplication_quality_score=1.0,
            token_structure_score=1.0,
            text_density_score=1.0,
            order_plausibility_score=1.0,
            image_compatibility_score=1.0,
        ),
    )


def test_page_level_routing_survives_document_escalation() -> None:
    """One defective page must not force sibling accepted pages into OCR."""

    from backend.app.contracts.geometry import (
        Geometry,
        NormalisedBoundingBox,
        NormalisedPolygon,
    )
    from backend.app.contracts.native import (
        NativeWord,
        PdfPointBox,
        RecognitionMethod,
        RecognitionStatus,
    )

    def _word(page: int, idx: int) -> NativeWord:
        x, y, w, h = 0.1, 0.1 + idx * 0.05, 0.2, 0.04
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
            id=f"word_p{page:04d}_{idx:06d}",
            page_number=page,
            sequence_index=idx,
            text="Hello",
            normalised_text="Hello",
            character_ids=[],
            geometry=Geometry(bbox=bbox, polygon=polygon),
            pdf_point_bbox=PdfPointBox(x=72, y=700, width=40, height=12),
            upright=True,
            recognition_method=RecognitionMethod.NATIVE_PDF,
            source_mode=SourceMode.NATIVE_AUTHORITY,
            recognition_status=RecognitionStatus.ACCEPTED,
        )

    def _accepted(page: int) -> NativePageResult:
        trust = NativePageTrustResult(
            page_number=page,
            decision=NativePageDecision.ACCEPTED,
            source_mode=SourceMode.NATIVE_AUTHORITY,
            native_text_present=True,
            native_trust_score=0.95,
            trust_policy_version="phase3-v1.6",
            hard_rejection=False,
            duplicate_hard_rejection=False,
            reason_codes=[],
            metrics=_empty_metrics(),
            visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
            native_result_available=True,
            visual_processing_required=False,
        )
        return NativePageResult(
            page_number=page,
            decision=NativePageDecision.ACCEPTED,
            source_mode=SourceMode.NATIVE_AUTHORITY,
            trust=trust,
            words=[_word(page, 0), _word(page, 1)],
        )

    def _rejected(page: int) -> NativePageResult:
        trust = NativePageTrustResult(
            page_number=page,
            decision=NativePageDecision.REJECTED,
            source_mode=SourceMode.VISUAL_AUTHORITY,
            native_text_present=True,
            native_trust_score=0.2,
            trust_policy_version="phase3-v1.6",
            hard_rejection=True,
            duplicate_hard_rejection=True,
            reason_codes=[NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value],
            metrics=_empty_metrics(),
            visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
            native_result_available=False,
            visual_processing_required=True,
        )
        return NativePageResult(
            page_number=page,
            decision=NativePageDecision.REJECTED,
            source_mode=SourceMode.VISUAL_AUTHORITY,
            trust=trust,
            words=[],
            verification_words=as_verification_words([_word(page, 0)]),
        )

    pages = [_accepted(1), _rejected(2), _rejected(3), _accepted(4)]
    policy = NativeTrustPolicyConfig()
    doc_policy = decide_document_policy(
        [p.trust for p in pages], policy=policy, all_pages_image_source=False
    )
    assert doc_policy.value == "visual_authority"
    escalated = apply_document_escalation(pages, document_policy=doc_policy)
    clean = escalated[0]
    assert is_recoverable_escalation_suppressed(clean)
    restored = restore_escalation_suppressed_native(clean)
    assert restored.decision is NativePageDecision.ACCEPTED
    assert restored.words
    assert is_trusted_digital_native(restored, visibility=None, image_dominant=False)
    # Sibling defective pages remain rejected / not recovered as digital native.
    assert not is_recoverable_escalation_suppressed(escalated[1])
