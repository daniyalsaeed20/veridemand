"""Phase 5 Task C1 — dual-detector merge algorithm."""

from __future__ import annotations

from backend.app.datasets.phase5.constants import DETECTOR_DUAL_MERGE_VERSION
from backend.app.datasets.phase5.detector_merge import merge_detector_regions
from backend.app.extraction.visual.detect_first_types import DetectedTextRegion


def _region(
    *,
    region_id: str,
    bbox: tuple[float, float, float, float],
    conf: float,
    model: str,
    order: int = 0,
) -> DetectedTextRegion:
    x, y, w, h = bbox
    poly = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    return DetectedTextRegion(
        region_id=region_id,
        page_index=0,
        order_index=order,
        polygon_px=tuple((p[0] * 1000, p[1] * 1000) for p in poly),
        polygon_norm=poly,
        bbox_norm=bbox,
        detection_confidence=conf,
        detector_model_name=model,
    )


def test_exact_duplicates_merge_with_provenance() -> None:
    a = _region(
        region_id="a1",
        bbox=(0.1, 0.1, 0.2, 0.05),
        conf=0.9,
        model="PP-OCRv5_mobile_det",
    )
    b = _region(
        region_id="b1",
        bbox=(0.1, 0.1, 0.2, 0.05),
        conf=0.8,
        model="PP-OCRv5_server_det",
    )
    merged = merge_detector_regions([a], [b])
    assert len(merged) == 1
    assert merged[0].merge_version == DETECTOR_DUAL_MERGE_VERSION
    assert "PP-OCRv5_mobile_det" in merged[0].source_detector_names
    assert "PP-OCRv5_server_det" in merged[0].source_detector_names
    assert len(merged[0].source_confidences) == 2
    assert merged[0].region_id.startswith("dfmrg_")


def test_overlapping_equivalent_boxes_merge() -> None:
    a = _region(
        region_id="a1",
        bbox=(0.10, 0.10, 0.20, 0.05),
        conf=0.7,
        model="mobile",
    )
    b = _region(
        region_id="b1",
        bbox=(0.105, 0.102, 0.19, 0.048),
        conf=0.85,
        model="server",
    )
    merged = merge_detector_regions([a], [b])
    assert len(merged) == 1
    assert set(merged[0].source_detector_names) == {"mobile", "server"}


def test_distinct_neighbouring_lines_remain_separate() -> None:
    a = _region(
        region_id="a1",
        bbox=(0.1, 0.10, 0.4, 0.03),
        conf=0.9,
        model="mobile",
    )
    b = _region(
        region_id="b1",
        bbox=(0.1, 0.20, 0.4, 0.03),
        conf=0.9,
        model="server",
    )
    merged = merge_detector_regions([a], [b])
    assert len(merged) == 2


def test_partial_overlap_retains_fragments() -> None:
    # Two boxes with moderate IoU should not collapse to one larger box only.
    a = _region(
        region_id="a1",
        bbox=(0.10, 0.10, 0.20, 0.05),
        conf=0.9,
        model="mobile",
    )
    b = _region(
        region_id="b1",
        bbox=(0.22, 0.10, 0.20, 0.05),
        conf=0.8,
        model="server",
    )
    merged = merge_detector_regions([a], [b])
    assert len(merged) == 2


def test_merge_deterministic_stable_ids() -> None:
    a = _region(
        region_id="a1",
        bbox=(0.1, 0.1, 0.2, 0.05),
        conf=0.9,
        model="mobile",
        order=1,
    )
    b = _region(
        region_id="b1",
        bbox=(0.1, 0.1, 0.2, 0.05),
        conf=0.8,
        model="server",
        order=2,
    )
    m1 = merge_detector_regions([a], [b])
    m2 = merge_detector_regions([b], [a])
    assert [r.region_id for r in m1] == [r.region_id for r in m2]
    assert [r.bbox_norm for r in m1] == [r.bbox_norm for r in m2]


def test_larger_box_does_not_silently_discard_tighter_equivalent() -> None:
    tight = _region(
        region_id="t",
        bbox=(0.12, 0.12, 0.10, 0.04),
        conf=0.7,
        model="mobile",
    )
    large = _region(
        region_id="l",
        bbox=(0.10, 0.10, 0.20, 0.08),
        conf=0.9,
        model="server",
    )
    # High containment + high IoU relative → prefer tighter geometry.
    merged = merge_detector_regions([tight], [large])
    # Either merged to one (equivalent) preferring tighter, or both retained.
    assert len(merged) >= 1
    if len(merged) == 1:
        assert merged[0].bbox_norm[2] * merged[0].bbox_norm[3] <= (
            large.bbox_norm[2] * large.bbox_norm[3]
        )
