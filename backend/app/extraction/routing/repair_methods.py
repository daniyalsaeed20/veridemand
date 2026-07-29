"""Repair method execution: recognition-only and local detection+recognition."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.contracts.native import NativeWord
from backend.app.contracts.ocr import HandwritingAssessment
from backend.app.contracts.repair import (
    RepairMethod,
    RepairRegionExecutionDiagnostics,
    RepairRegionRecord,
)
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.repair_coordinates import (
    RepairCropTransform,
    build_crop_transform,
    map_repaired_crop_polygon,
    word_bbox_to_crop_pixels,
)
from backend.app.extraction.routing.repair_reconcile import RepairedWordCandidate
from PIL import Image

logger = logging.getLogger("veridemand.routing.repair_methods")

# Callbacks never receive or return private paths; recognition text stays in-process only.
RecogniseCropFn = Callable[[Image.Image], tuple[str, float]]
DetectRecogniseFn = Callable[
    [Image.Image, int | None], list[tuple[str, float, list[tuple[float, float]]]]
]


@dataclass(slots=True)
class RegionRepairOutcome:
    region: RepairRegionRecord
    method: RepairMethod
    candidates: list[RepairedWordCandidate]
    diagnostics: RepairRegionExecutionDiagnostics
    crop_closed: bool = True


def _crop_image(image: Image.Image, transform: RepairCropTransform) -> Image.Image:
    x0, y0, x1, y1 = transform.crop_box_px
    return image.crop((x0, y0, x1, y1))


def _looks_handwritten_ink(crop: Image.Image) -> bool:
    """Cheap heuristic: high stroke irregularity → pending Phase 5, not printed authority.

    Does not claim HTR; only flags that printed repair should stay provisional.
    """

    try:
        gray = crop.convert("L")
        # Downsample for speed.
        sample = gray.resize((min(64, gray.width), min(64, gray.height)))
        pixels = list(sample.getdata())
        if not pixels:
            return False
        mean = sum(pixels) / len(pixels)
        var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        # Handwritten ink on forms often has mid variance without grid structure.
        dark = sum(1 for p in pixels if p < 90) / len(pixels)
        return var > 1800 and 0.02 < dark < 0.25 and sample.width * sample.height > 200
    except Exception:
        return False


def repair_region_recognition_only(
    page_image: Image.Image,
    words: Sequence[NativeWord],
    region: RepairRegionRecord,
    *,
    transform: RepairCropTransform,
    recognise_crop: RecogniseCropFn,
    batch_size: int,
) -> RegionRepairOutcome:
    """Bypass detection; recognise tightly cropped known word boxes."""

    started = time.perf_counter()
    candidates: list[RepairedWordCandidate] = []
    word_by_id = {w.id: w for w in words}
    crops: list[tuple[NativeWord, Image.Image]] = []
    region_crop = _crop_image(page_image, transform)
    try:
        _ = _looks_handwritten_ink(region_crop)
        for wid in region.source_word_ids:
            word = word_by_id.get(wid)
            if word is None or word.geometry is None:
                continue
            lx0, ly0, lx1, ly1 = word_bbox_to_crop_pixels(word.geometry.bbox, transform)
            word_crop = region_crop.crop((lx0, ly0, lx1, ly1))
            crops.append((word, word_crop))

        for start in range(0, len(crops), max(1, batch_size)):
            chunk = crops[start : start + max(1, batch_size)]
            for word, word_crop in chunk:
                try:
                    text, score = recognise_crop(word_crop)
                    text = (text or "").strip()
                    if not text:
                        continue
                    polygon, bbox, geometry, pixel_polygon, pixel_bbox = map_repaired_crop_polygon(
                        _word_quad_in_crop(word.geometry.bbox, transform),
                        transform,
                    )
                    candidates.append(
                        RepairedWordCandidate(
                            text=text,
                            recognition_score=float(score),
                            polygon=polygon,
                            bbox=bbox,
                            geometry=geometry,
                            pixel_polygon=pixel_polygon,
                            pixel_bbox=pixel_bbox,
                            method=RepairMethod.RECOGNITION_ONLY,
                            repair_region_id=region.repair_region_id,
                            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        )
                    )
                finally:
                    word_crop.close()
    finally:
        region_crop.close()

    duration_ms = int((time.perf_counter() - started) * 1000)
    diag = RepairRegionExecutionDiagnostics(
        repair_region_id=region.repair_region_id,
        page_number=region.page_number,
        method=RepairMethod.RECOGNITION_ONLY,
        crop_width=transform.crop_width_px,
        crop_height=transform.crop_height_px,
        detector_limit_side=None,
        recognition_batch_size=max(1, batch_size),
        duration_ms=duration_ms,
        result_count=len(candidates),
        quality_status=None,
        reason_codes=["recognition_only_completed"] if candidates else ["recognition_only_empty"],
    )
    logger.info(
        "targeted_repair_region",
        extra={
            "repair_region_id": region.repair_region_id,
            "page_number": region.page_number,
            "method": RepairMethod.RECOGNITION_ONLY.value,
            "crop_width": transform.crop_width_px,
            "crop_height": transform.crop_height_px,
            "result_count": len(candidates),
            "duration_ms": duration_ms,
        },
    )
    return RegionRepairOutcome(
        region=region, method=RepairMethod.RECOGNITION_ONLY, candidates=candidates, diagnostics=diag
    )


def _word_quad_in_crop(
    bbox: NormalisedBoundingBox, transform: RepairCropTransform
) -> list[tuple[float, float]]:
    lx0, ly0, lx1, ly1 = word_bbox_to_crop_pixels(bbox, transform)
    return [
        (float(lx0), float(ly0)),
        (float(lx1), float(ly0)),
        (float(lx1), float(ly1)),
        (float(lx0), float(ly1)),
    ]


def repair_region_local_detection(
    page_image: Image.Image,
    region: RepairRegionRecord,
    *,
    transform: RepairCropTransform,
    detect_recognise: DetectRecogniseFn,
    detector_limit_side: int,
) -> RegionRepairOutcome:
    """Detect+recognise inside the padded crop only (never full-page detection)."""

    started = time.perf_counter()
    candidates: list[RepairedWordCandidate] = []
    crop = _crop_image(page_image, transform)
    try:
        hw_pending = _looks_handwritten_ink(crop)
        raw_items = detect_recognise(crop, detector_limit_side)
        for text, score, poly_crop in raw_items:
            text = (text or "").strip()
            if not text or len(poly_crop) < 3:
                continue
            try:
                polygon, bbox, geometry, pixel_polygon, pixel_bbox = map_repaired_crop_polygon(
                    poly_crop, transform
                )
            except Exception:
                continue
            candidates.append(
                RepairedWordCandidate(
                    text=text,
                    recognition_score=float(score),
                    polygon=polygon,
                    bbox=bbox,
                    geometry=geometry,
                    pixel_polygon=pixel_polygon,
                    pixel_bbox=pixel_bbox,
                    method=RepairMethod.LOCAL_DETECTION_AND_RECOGNITION,
                    repair_region_id=region.repair_region_id,
                    handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                )
            )
        if hw_pending and candidates:
            # Printed repair remains provisional; handwriting stays pending Phase 5.
            for c in candidates:
                c.handwriting_assessment = HandwritingAssessment.PENDING_PHASE_5
    finally:
        crop.close()

    duration_ms = int((time.perf_counter() - started) * 1000)
    diag = RepairRegionExecutionDiagnostics(
        repair_region_id=region.repair_region_id,
        page_number=region.page_number,
        method=RepairMethod.LOCAL_DETECTION_AND_RECOGNITION,
        crop_width=transform.crop_width_px,
        crop_height=transform.crop_height_px,
        detector_limit_side=detector_limit_side,
        recognition_batch_size=1,
        duration_ms=duration_ms,
        result_count=len(candidates),
        reason_codes=["local_detection_completed"] if candidates else ["local_detection_empty"],
    )
    logger.info(
        "targeted_repair_region",
        extra={
            "repair_region_id": region.repair_region_id,
            "page_number": region.page_number,
            "method": RepairMethod.LOCAL_DETECTION_AND_RECOGNITION.value,
            "crop_width": transform.crop_width_px,
            "crop_height": transform.crop_height_px,
            "result_count": len(candidates),
            "duration_ms": duration_ms,
        },
    )
    return RegionRepairOutcome(
        region=region,
        method=RepairMethod.LOCAL_DETECTION_AND_RECOGNITION,
        candidates=candidates,
        diagnostics=diag,
    )


def build_page_transform_for_region(
    region: RepairRegionRecord,
    *,
    page_width_px: int,
    page_height_px: int,
    page_width_points: float,
    page_height_points: float,
    render_scale: float,
    intrinsic_rotation: int,
) -> RepairCropTransform:
    return build_crop_transform(
        region.expanded_normalised_bbox,
        page_width_px=page_width_px,
        page_height_px=page_height_px,
        page_width_points=page_width_points,
        page_height_points=page_height_points,
        render_scale=render_scale,
        intrinsic_rotation=intrinsic_rotation,
    )


def execute_regions(
    page_image: Image.Image,
    words: Sequence[NativeWord],
    regions: Sequence[RepairRegionRecord],
    policy: RoutingPolicy,
    *,
    method: RepairMethod,
    page_width_points: float,
    page_height_points: float,
    render_scale: float,
    intrinsic_rotation: int,
    recognise_crop: RecogniseCropFn,
    detect_recognise: DetectRecogniseFn,
) -> list[RegionRepairOutcome]:
    """Run each repair region with the selected method."""

    outcomes: list[RegionRepairOutcome] = []
    for region in regions:
        transform = build_page_transform_for_region(
            region,
            page_width_px=page_image.width,
            page_height_px=page_image.height,
            page_width_points=page_width_points,
            page_height_points=page_height_points,
            render_scale=render_scale,
            intrinsic_rotation=intrinsic_rotation,
        )
        if method is RepairMethod.RECOGNITION_ONLY:
            outcomes.append(
                repair_region_recognition_only(
                    page_image,
                    words,
                    region,
                    transform=transform,
                    recognise_crop=recognise_crop,
                    batch_size=policy.recognition_batch_size,
                )
            )
        else:
            outcomes.append(
                repair_region_local_detection(
                    page_image,
                    region,
                    transform=transform,
                    detect_recognise=detect_recognise,
                    detector_limit_side=policy.primary_limit_side,
                )
            )
    return outcomes
