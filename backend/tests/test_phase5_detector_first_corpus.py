"""Detector-first corpus helpers — retention, determinism, privacy aggregates."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.detector_first import (
    apply_recognition_metadata,
    build_aggregate_report,
    build_region_crop,
    mark_exact_duplicates,
    process_page_regions,
)
from backend.app.datasets.phase5.detector_first_schemas import DetectorFirstRegionRecord
from backend.app.datasets.phase5.padding import apply_crop_padding
from backend.app.datasets.phase5.schemas import AppliedPadding
from backend.app.extraction.visual.detect_first_types import (
    DetectedTextRegion,
    RecognisedCropResult,
)


def _region(
    region_id: str, bbox: tuple[float, float, float, float], order: int = 0
) -> DetectedTextRegion:
    x, y, w, h = bbox
    poly = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
    return DetectedTextRegion(
        region_id=region_id,
        page_index=0,
        order_index=order,
        polygon_px=tuple((p[0] * 100, p[1] * 100) for p in poly),
        polygon_norm=poly,
        bbox_norm=bbox,
        detection_confidence=0.9,
        detector_model_name="PP-OCRv5_mobile_det",
        detector_version="3.7.2",
    )


def _page() -> Image.Image:
    image = Image.new("RGB", (100, 100), (255, 255, 255))
    ImageDraw.Draw(image).rectangle((10, 10, 40, 30), fill=(0, 0, 0))
    return image


def test_empty_and_failed_recognition_retained(tmp_path: Path) -> None:
    page = _page()
    regions = [_region("dfreg_aaaaaaaaaaaaaaaa", (0.1, 0.1, 0.3, 0.2), 0)]

    def recognise(crops: list[tuple[str, Image.Image]]) -> list[RecognisedCropResult]:
        return [
            RecognisedCropResult(
                region_id=crops[0][0],
                status="empty",
                confidence=0.0,
                recognizer_model_name="PP-OCRv5_mobile_rec",
            )
        ]

    records = process_page_regions(
        private_root=tmp_path,
        page=page,
        page_id="page_abcdefghijklmnop",
        document_id="doc_abcdefghijklmnop",
        source_group_id="srcgrp_abcdefghijkl",
        page_index=0,
        regions=regions,
        recognise=recognise,
        low_thr=0.75,
        min_thr=0.3,
    )
    assert len(records) == 1
    assert records[0].recognition_status == "empty"
    assert (tmp_path / records[0].crop_relpath).is_file()

    failed = apply_recognition_metadata(
        records[0],
        RecognisedCropResult(
            region_id=records[0].region_id,
            status="failed",
            confidence=None,
            recognizer_model_name="PP-OCRv5_mobile_rec",
            failure_reason="boom",
        ),
        low_thr=0.75,
        min_thr=0.3,
    )
    assert failed.recognition_status == "failed"
    report = build_aggregate_report([failed])
    assert report["failed_recognition"] == 1
    assert "text" not in report
    blob = str(report)
    assert "dfreg_" not in blob or "region_id" not in report


def test_deterministic_crops_and_idempotent_rerun(tmp_path: Path) -> None:
    page = _page()
    region = _region("dfreg_bbbbbbbbbbbbbbbb", (0.1, 0.1, 0.2, 0.15))
    a, data_a = build_region_crop(
        page=page,
        region=region,
        page_id="page_abcdefghijklmnop",
        document_id="doc_abcdefghijklmnop",
        source_group_id="srcgrp_abcdefghijkl",
        page_render_sha256="a" * 64,
        crop_relpath="detector-first/crops/a.png",
    )
    b, data_b = build_region_crop(
        page=page,
        region=region,
        page_id="page_abcdefghijklmnop",
        document_id="doc_abcdefghijklmnop",
        source_group_id="srcgrp_abcdefghijkl",
        page_render_sha256="a" * 64,
        crop_relpath="detector-first/crops/a.png",
    )
    assert a.crop_sha256 == b.crop_sha256
    assert data_a == data_b
    assert a.source_bbox == b.source_bbox


def test_exact_duplicate_handling() -> None:
    now = datetime.now(UTC)
    pad = AppliedPadding(pad_ratio=0.08, pad_x=0.01, pad_y=0.01, clamped=False)
    bbox = NormalisedBoundingBox(x=0.1, y=0.1, width=0.2, height=0.1)

    def make(region_id: str, order: int) -> DetectorFirstRegionRecord:
        return DetectorFirstRegionRecord(
            region_id=region_id,
            crop_id=f"crop_{region_id[-8:]}zzzzzz",
            source_group_id="srcgrp_abcdefghijkl",
            document_id="doc_abcdefghijklmnop",
            page_id="page_abcdefghijklmnop",
            page_index=0,
            order_index=order,
            source_bbox=bbox,
            crop_bbox=apply_crop_padding(bbox)[0],
            applied_padding=pad,
            crop_relpath=f"detector-first/crops/{region_id}.png",
            crop_sha256="ab" * 32,
            page_render_sha256="cd" * 32,
            perceptual_hash="0123456789abcdef",
            width_px=10,
            height_px=10,
            detection_confidence=0.9,
            detector_model_name="PP-OCRv5_mobile_det",
            created_at=now,
        )

    marked = mark_exact_duplicates(
        [make("dfreg_1111111111111111", 1), make("dfreg_0000000000000000", 0)]
    )
    canonical = [r for r in marked if r.duplicate_of_region_id is None]
    assert len(canonical) == 1
    assert sum(1 for r in marked if r.duplicate_of_region_id is not None) == 1


def test_aggregate_report_has_no_ocr_text() -> None:
    now = datetime.now(UTC)
    pad = AppliedPadding(pad_ratio=0.08, pad_x=0.01, pad_y=0.01, clamped=False)
    bbox = NormalisedBoundingBox(x=0.1, y=0.1, width=0.2, height=0.1)
    record = DetectorFirstRegionRecord(
        region_id="dfreg_cccccccccccccccc",
        crop_id="crop_cccccccczzzzzz",
        source_group_id="srcgrp_abcdefghijkl",
        document_id="doc_abcdefghijklmnop",
        page_id="page_abcdefghijklmnop",
        page_index=0,
        order_index=0,
        source_bbox=bbox,
        crop_bbox=apply_crop_padding(bbox)[0],
        applied_padding=pad,
        crop_relpath="detector-first/crops/x.png",
        crop_sha256="11" * 32,
        page_render_sha256="22" * 32,
        perceptual_hash="0123456789abcdef",
        width_px=10,
        height_px=10,
        detection_confidence=0.9,
        detector_model_name="PP-OCRv5_mobile_det",
        recognition_status="recognised",
        recognition_confidence_band="high",
        created_at=now,
    )
    report = build_aggregate_report([record])
    serialised = str(report)
    assert "secret" not in serialised
    assert "rec_text" not in serialised
    assert report["recognised"] == 1
