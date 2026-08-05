"""Strict label-transfer rules for detector-first crops."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.detector_first import transfer_labels
from backend.app.datasets.phase5.detector_first_schemas import DetectorFirstRegionRecord
from backend.app.datasets.phase5.padding import apply_crop_padding
from backend.app.datasets.phase5.schemas import AppliedPadding, CropRecord


def _crop(
    *,
    sha: str,
    bbox: NormalisedBoundingBox,
    crop_bbox: NormalisedBoundingBox | None = None,
    page_id: str = "page_abcdefghijklmnop",
) -> CropRecord:
    pad = AppliedPadding(pad_ratio=0.08, pad_x=0.01, pad_y=0.01, clamped=False)
    cb = crop_bbox or apply_crop_padding(bbox)[0]
    return CropRecord(
        crop_id="crop_" + sha[:16],
        source_group_id="srcgrp_abcdefghijkl",
        document_id="doc_abcdefghijklmnop",
        page_id=page_id,
        page_index=0,
        candidate_source="full_page_ocr",
        source_bbox=bbox,
        crop_bbox=cb,
        applied_padding=pad,
        crop_relpath=f"crops/{sha[:8]}.png",
        sha256=sha,
        perceptual_hash="0123456789abcdef",
        width_px=20,
        height_px=10,
        created_at=datetime.now(UTC),
    )


def _det(
    *,
    sha: str,
    bbox: NormalisedBoundingBox,
    crop_bbox: NormalisedBoundingBox | None = None,
) -> DetectorFirstRegionRecord:
    pad = AppliedPadding(pad_ratio=0.08, pad_x=0.01, pad_y=0.01, clamped=False)
    cb = crop_bbox or apply_crop_padding(bbox)[0]
    return DetectorFirstRegionRecord(
        region_id="dfreg_" + sha[:16],
        crop_id="crop_df" + sha[:14],
        source_group_id="srcgrp_abcdefghijkl",
        document_id="doc_abcdefghijklmnop",
        page_id="page_abcdefghijklmnop",
        page_index=0,
        order_index=0,
        source_bbox=bbox,
        crop_bbox=cb,
        applied_padding=pad,
        crop_relpath=f"detector-first/crops/{sha[:8]}.png",
        crop_sha256=sha,
        page_render_sha256="aa" * 32,
        perceptual_hash="0123456789abcdef",
        width_px=20,
        height_px=10,
        detection_confidence=0.9,
        detector_model_name="PP-OCRv5_mobile_det",
        created_at=datetime.now(UTC),
    )


def test_exact_hash_transfer() -> None:
    sha = "ab" * 32
    bbox = NormalisedBoundingBox(x=0.1, y=0.1, width=0.2, height=0.1)
    transfers, counts = transfer_labels(
        detector_records=[_det(sha=sha, bbox=bbox)],
        labelled_crops=[_crop(sha=sha, bbox=bbox)],
        labels_by_crop_sha={sha: "printed"},
    )
    assert len(transfers) == 1
    assert transfers[0].method == "exact_crop_sha256"
    assert transfers[0].label == "printed"
    assert counts["exact_sha"] == 1


def test_strict_geometry_transfer() -> None:
    old_sha = "11" * 32
    new_sha = "22" * 32
    bbox = NormalisedBoundingBox(x=0.10, y=0.10, width=0.20, height=0.10)
    near = NormalisedBoundingBox(x=0.10005, y=0.10005, width=0.20, height=0.10)
    transfers, counts = transfer_labels(
        detector_records=[_det(sha=new_sha, bbox=near)],
        labelled_crops=[_crop(sha=old_sha, bbox=bbox)],
        labels_by_crop_sha={old_sha: "handwritten"},
    )
    assert len(transfers) == 1
    assert transfers[0].method == "strict_geometry"
    assert transfers[0].label == "handwritten"
    assert counts["strict_geometry"] == 1


def test_loose_overlap_rejected() -> None:
    old_sha = "33" * 32
    new_sha = "44" * 32
    bbox = NormalisedBoundingBox(x=0.10, y=0.10, width=0.20, height=0.10)
    # IoU ~0.56 — above loose threshold, below strict identity.
    loose = NormalisedBoundingBox(x=0.14, y=0.11, width=0.20, height=0.10)
    transfers, counts = transfer_labels(
        detector_records=[_det(sha=new_sha, bbox=loose)],
        labelled_crops=[_crop(sha=old_sha, bbox=bbox)],
        labels_by_crop_sha={old_sha: "uncertain"},
    )
    assert transfers == []
    assert counts.get("loose_overlap_rejected", 0) >= 1


def test_differing_crop_framing_remains_unlabelled() -> None:
    old_sha = "55" * 32
    new_sha = "66" * 32
    bbox = NormalisedBoundingBox(x=0.10, y=0.10, width=0.20, height=0.10)
    # Same source geometry but materially different crop window.
    old_crop_bbox = NormalisedBoundingBox(x=0.08, y=0.08, width=0.24, height=0.14)
    new_crop_bbox = NormalisedBoundingBox(x=0.02, y=0.02, width=0.40, height=0.30)
    transfers, counts = transfer_labels(
        detector_records=[_det(sha=new_sha, bbox=bbox, crop_bbox=new_crop_bbox)],
        labelled_crops=[_crop(sha=old_sha, bbox=bbox, crop_bbox=old_crop_bbox)],
        labels_by_crop_sha={old_sha: "non_text"},
    )
    assert transfers == []
    assert counts.get("framing_differs_unlabelled", 0) == 1
