"""Targeted-repair quality gate."""

from __future__ import annotations

from collections.abc import Sequence

from backend.app.contracts.repair import (
    REPAIR_POLICY_VERSION,
    RepairQualityEvidence,
    RepairQualityStatus,
    RepairRegionRecord,
)
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.repair_reconcile import RepairedWordCandidate


def evaluate_repair_quality(
    *,
    page_number: int,
    regions: Sequence[RepairRegionRecord],
    repaired: Sequence[RepairedWordCandidate],
    policy: RoutingPolicy,
    expected_failed_word_count: int,
) -> RepairQualityEvidence:
    """Gate a staged repair result before atomic publication."""

    reasons: list[str] = []
    if not repaired:
        return RepairQualityEvidence(
            page_number=page_number,
            status=RepairQualityStatus.REPAIR_INSUFFICIENT,
            repaired_word_count=0,
            reason_codes=["no_repaired_words"],
            policy_version=policy.repair_policy_version or REPAIR_POLICY_VERSION,
            fallback_to_full_ocr=True,
        )

    scores = [max(0.0, min(1.0, c.recognition_score)) for c in repaired]
    mean_conf = sum(scores) / len(scores)
    low_ratio = sum(1 for s in scores if s < 0.5) / len(scores)
    geometry_valid = sum(1 for c in repaired if c.bbox.width > 0 and c.bbox.height > 0) / len(
        repaired
    )

    # Approximate region coverage: repaired union vs region expanded area.
    region_area = sum(r.page_coverage_ratio for r in regions) or 1e-9
    repaired_area = sum(c.bbox.width * c.bbox.height for c in repaired)
    region_coverage = min(1.0, repaired_area / region_area)

    # Near-duplicate overlap among repaired candidates.
    dup = 0
    for i, a in enumerate(repaired):
        for b in repaired[i + 1 :]:
            ax1, ay1 = a.bbox.x + a.bbox.width, a.bbox.y + a.bbox.height
            bx1, by1 = b.bbox.x + b.bbox.width, b.bbox.y + b.bbox.height
            ix0, iy0 = max(a.bbox.x, b.bbox.x), max(a.bbox.y, b.bbox.y)
            ix1, iy1 = min(ax1, bx1), min(ay1, by1)
            inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
            if inter > 0 and inter / max(1e-12, a.bbox.width * a.bbox.height) >= 0.6:
                dup += 1
    pairs = max(1, len(repaired) * (len(repaired) - 1) // 2)
    dup_ratio = dup / pairs if repaired else 0.0

    # Fragmentation: too many tiny tokens vs failed count.
    tiny = sum(1 for c in repaired if len(c.text.strip()) <= 1)
    frag = tiny / max(1, len(repaired))

    status = RepairQualityStatus.REPAIR_COMPLETE
    if mean_conf < policy.repair_min_mean_confidence:
        reasons.append("mean_confidence_below_min")
        status = RepairQualityStatus.REPAIR_INSUFFICIENT
    if low_ratio > policy.repair_max_low_confidence_ratio:
        reasons.append("low_confidence_ratio_high")
        status = RepairQualityStatus.REPAIR_INSUFFICIENT
    if geometry_valid < policy.repair_min_geometry_valid_ratio:
        reasons.append("geometry_valid_ratio_low")
        status = RepairQualityStatus.REPAIR_INSUFFICIENT
    if region_coverage < policy.repair_min_region_coverage and expected_failed_word_count >= 2:
        reasons.append("region_coverage_low")
        status = RepairQualityStatus.REPAIR_INSUFFICIENT
    if dup_ratio > policy.repair_max_duplicate_overlap:
        reasons.append("duplicate_overlap_high")
        if status is RepairQualityStatus.REPAIR_COMPLETE:
            status = RepairQualityStatus.REPAIR_COMPLETE_WITH_WARNINGS
        else:
            status = RepairQualityStatus.REPAIR_INSUFFICIENT
    if frag > 0.55 and len(repaired) > expected_failed_word_count * 3:
        reasons.append("fragmentation_high")
        if status is RepairQualityStatus.REPAIR_COMPLETE:
            status = RepairQualityStatus.REPAIR_COMPLETE_WITH_WARNINGS

    if status is RepairQualityStatus.REPAIR_COMPLETE and not reasons:
        reasons.append("repair_quality_passed")
    elif status is RepairQualityStatus.REPAIR_COMPLETE_WITH_WARNINGS:
        reasons.append("repair_quality_warnings")

    fallback = status in {
        RepairQualityStatus.REPAIR_INSUFFICIENT,
        RepairQualityStatus.REPAIR_FAILED,
    }
    return RepairQualityEvidence(
        page_number=page_number,
        status=status,
        mean_recognition_confidence=round(mean_conf, 6),
        geometry_valid_ratio=round(geometry_valid, 6),
        repaired_word_count=len(repaired),
        region_coverage_ratio=round(region_coverage, 6),
        remaining_unsupported_ink_ratio=0.0,
        duplicate_overlap_ratio=round(dup_ratio, 6),
        neighbour_agreement_score=None,
        fragmentation_score=round(frag, 6),
        low_confidence_ratio=round(low_ratio, 6),
        reason_codes=reasons,
        policy_version=policy.repair_policy_version or REPAIR_POLICY_VERSION,
        fallback_to_full_ocr=fallback,
    )
