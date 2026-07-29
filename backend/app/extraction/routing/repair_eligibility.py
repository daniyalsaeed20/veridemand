"""Typed targeted-repair eligibility evidence (Correction 6)."""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.contracts.native import NativeWord
from backend.app.contracts.repair import (
    REPAIR_POLICY_VERSION,
    BaseSourceMode,
    RepairMethod,
    RepairRegionRecord,
    TargetedRepairEligibilityEvidence,
)
from backend.app.extraction.routing.models import RoutingPolicy


def _bbox_area(bbox: NormalisedBoundingBox) -> float:
    return max(0.0, float(bbox.width) * float(bbox.height))


def _union_coverage(boxes: Sequence[NormalisedBoundingBox]) -> float:
    return min(1.0, sum(_bbox_area(b) for b in boxes))


def evaluate_targeted_repair_eligibility(
    *,
    page_number: int,
    words: Sequence[NativeWord],
    failed_indices: Sequence[int],
    regions: Sequence[RepairRegionRecord],
    policy: RoutingPolicy,
    visual_agreement_score: float | None,
    recognition_agreement_score: float | None,
    base_source_mode: BaseSourceMode = BaseSourceMode.VERIFIED_EMBEDDED,
    geometry_shifted: bool = False,
    coordinates_valid: bool = True,
) -> TargetedRepairEligibilityEvidence:
    """Decide whether bounded regional repair is cheaper and safer than full OCR."""

    policy_version = policy.repair_policy_version or REPAIR_POLICY_VERSION
    candidate_count = len(words)
    failed_set = {i for i in failed_indices if 0 <= i < candidate_count}
    failed_count = len(failed_set)
    verified_count = max(0, candidate_count - failed_count)
    fail_ratio = failed_count / max(1, candidate_count)

    region_coverage = min(1.0, sum(r.page_coverage_ratio for r in regions))
    largest = max((r.page_coverage_ratio for r in regions), default=0.0)
    retained_boxes = [
        w.geometry.bbox
        for i, w in enumerate(words)
        if i not in failed_set and w.geometry is not None
    ]
    all_boxes = [w.geometry.bbox for w in words if w.geometry is not None]
    retained_page_coverage = _union_coverage(retained_boxes) if retained_boxes else 0.0
    candidate_coverage = _union_coverage(all_boxes) if all_boxes else 0.0
    # Fraction of candidate ink retained (not absolute page area).
    retained_of_candidates = (
        retained_page_coverage / candidate_coverage if candidate_coverage > 1e-9 else 0.0
    )

    reasons: list[str] = []
    eligible = True

    if not policy.targeted_repair_enabled:
        eligible = False
        reasons.append("targeted_repair_disabled")
    if candidate_count < 1:
        eligible = False
        reasons.append("no_base_candidates")
    if not coordinates_valid:
        eligible = False
        reasons.append("invalid_coordinates")
    if failed_count < 1:
        eligible = False
        reasons.append("no_failed_words")
    if fail_ratio > policy.max_fail_ratio_for_repair:
        eligible = False
        reasons.append("fail_ratio_exceeds_max")
    if len(regions) > policy.max_repair_regions:
        eligible = False
        reasons.append("region_count_exceeds_max")
    if region_coverage > policy.max_repair_coverage:
        eligible = False
        reasons.append("region_coverage_exceeds_max")
    if largest > policy.max_largest_region_coverage:
        eligible = False
        reasons.append("largest_region_coverage_exceeds_max")
    if retained_of_candidates < policy.min_retained_coverage and candidate_count >= 8:
        eligible = False
        reasons.append("retained_coverage_below_min")
    if (
        visual_agreement_score is not None
        and visual_agreement_score < policy.min_visual_floor_for_repair
    ):
        eligible = False
        reasons.append("visual_agreement_below_repair_floor")
    # Most of the page must still pass verification.
    if verified_count / max(1, candidate_count) < (1.0 - policy.max_fail_ratio_for_repair):
        eligible = False
        reasons.append("majority_verification_failed")

    method: RepairMethod | None = None
    if eligible:
        method = (
            RepairMethod.LOCAL_DETECTION_AND_RECOGNITION
            if geometry_shifted
            else RepairMethod.RECOGNITION_ONLY
        )
        reasons.append("bounded_failures_repair_eligible")
        reasons.append(f"method_{method.value}")

    return TargetedRepairEligibilityEvidence(
        page_number=page_number,
        base_source_mode=base_source_mode,
        candidate_word_count=candidate_count,
        verified_word_count=verified_count,
        failed_word_count=failed_count,
        failed_region_count=len(regions),
        failed_region_coverage_ratio=round(region_coverage, 6),
        largest_region_coverage_ratio=round(largest, 6),
        retained_page_coverage_ratio=round(retained_of_candidates, 6),
        visual_agreement_score=visual_agreement_score,
        recognition_agreement_score=recognition_agreement_score,
        repair_eligible=eligible,
        repair_method=method,
        repair_reason_codes=reasons,
        full_ocr_fallback_required=not eligible,
        policy_version=policy_version,
    )
