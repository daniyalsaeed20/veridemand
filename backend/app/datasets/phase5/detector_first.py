"""Detector-first corpus helpers (no Paddle imports; injectable adapters).

Builds ``phase5-detector-first-regions-v1`` private crops from detector-owned
regions, retains recognition failures, and supports strict label transfer plus
handwriting-seed coverage aggregates.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image

from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPoint, NormalisedPolygon
from backend.app.datasets.phase5.constants import (
    CROP_PADDING_RATIO,
    DETECTOR_FIRST_COMPARE_IOU,
    DETECTOR_FIRST_CORPUS_VERSION,
    DETECTOR_FIRST_LOOSE_IOU,
    DETECTOR_FIRST_SEED_CONTAIN_IOU,
    DETECTOR_FIRST_SEED_EXACT_IOU,
    DETECTOR_FIRST_SEED_FRAGMENT_IOU,
    DETECTOR_FIRST_STRICT_BBOX_L_INF,
    DETECTOR_FIRST_STRICT_IOU,
)
from backend.app.datasets.phase5.detector_first_schemas import (
    DetectorFirstLabelTransferRecord,
    DetectorFirstRegionRecord,
    SeedCoverageKind,
    confidence_band,
)
from backend.app.datasets.phase5.geometry_match import (
    bbox_from_tuple,
    bbox_iou,
    bbox_l_inf,
    containment_ratio,
)
from backend.app.datasets.phase5.hashes import png_bytes_and_hashes, sha256_file
from backend.app.datasets.phase5.ids import new_crop_id
from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.padding import apply_crop_padding
from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, reports_dir
from backend.app.datasets.phase5.schemas import CropRecord, HandwritingSeedRecord, SourceRecord
from backend.app.extraction.visual.detect_first_types import (
    DetectedTextRegion,
    RecognisedCropResult,
)

DetectFn = Callable[[Image.Image, int], list[DetectedTextRegion]]
RecogniseFn = Callable[[list[tuple[str, Image.Image]]], list[RecognisedCropResult]]


def _now() -> datetime:
    return datetime.now(UTC)


def _crop_pixels(page: Image.Image, bbox: NormalisedBoundingBox) -> Image.Image:
    w, h = page.size
    x0 = int(max(0, min(w - 1, round(bbox.x * w))))
    y0 = int(max(0, min(h - 1, round(bbox.y * h))))
    x1 = int(max(x0 + 1, min(w, round((bbox.x + bbox.width) * w))))
    y1 = int(max(y0 + 1, min(h, round((bbox.y + bbox.height) * h))))
    return page.crop((x0, y0, x1, y1))


def polygon_from_norm(
    points: tuple[tuple[float, float], ...] | list[tuple[float, float]],
) -> NormalisedPolygon:
    return NormalisedPolygon(points=[NormalisedPoint(x=float(x), y=float(y)) for x, y in points])


def build_region_crop(
    *,
    page: Image.Image,
    region: DetectedTextRegion,
    page_id: str,
    document_id: str,
    source_group_id: str,
    page_render_sha256: str,
    crop_relpath: str,
) -> tuple[DetectorFirstRegionRecord, bytes]:
    """Create one padded crop for a detector region (no recognition yet)."""

    source_bbox = bbox_from_tuple(region.bbox_norm)
    crop_bbox, applied = apply_crop_padding(source_bbox, pad_ratio=CROP_PADDING_RATIO)
    crop_img = _crop_pixels(page, crop_bbox)
    data, sha, phash = png_bytes_and_hashes(crop_img)
    record = DetectorFirstRegionRecord(
        region_id=region.region_id,
        crop_id=new_crop_id(),
        source_group_id=source_group_id,
        document_id=document_id,
        page_id=page_id,
        page_index=region.page_index,
        order_index=region.order_index,
        source_bbox=source_bbox,
        source_polygon=polygon_from_norm(region.polygon_norm),
        crop_bbox=crop_bbox,
        applied_padding=applied,
        crop_relpath=crop_relpath,
        crop_sha256=sha,
        page_render_sha256=page_render_sha256,
        perceptual_hash=phash,
        width_px=int(crop_img.size[0]),
        height_px=int(crop_img.size[1]),
        detection_confidence=float(region.detection_confidence),
        detector_model_name=region.detector_model_name,
        recognition_status="not_run",
        recognition_confidence_band="none",
        created_at=_now(),
    )
    return record, data


def apply_recognition_metadata(
    record: DetectorFirstRegionRecord,
    result: RecognisedCropResult,
    *,
    low_thr: float,
    min_thr: float,
) -> DetectorFirstRegionRecord:
    """Attach recognition status/confidence band; never store text on the record."""

    band = confidence_band(result.confidence, low_thr=low_thr, min_thr=min_thr)
    return record.model_copy(
        update={
            "recognition_status": result.status,
            "recognition_confidence_band": band,
        }
    )


def mark_exact_duplicates(
    records: list[DetectorFirstRegionRecord],
) -> list[DetectorFirstRegionRecord]:
    """Keep first region per crop SHA-256; mark later ones as duplicates."""

    by_sha: dict[str, str] = {}
    out: list[DetectorFirstRegionRecord] = []
    for record in sorted(records, key=lambda r: (r.page_index, r.order_index, r.region_id)):
        canonical = by_sha.get(record.crop_sha256)
        if canonical is None:
            by_sha[record.crop_sha256] = record.region_id
            out.append(record.model_copy(update={"duplicate_of_region_id": None}))
        else:
            out.append(record.model_copy(update={"duplicate_of_region_id": canonical}))
    return out


def transfer_labels(
    *,
    detector_records: Iterable[DetectorFirstRegionRecord],
    labelled_crops: Iterable[CropRecord],
    labels_by_crop_sha: dict[str, str],
    strict_l_inf: float = DETECTOR_FIRST_STRICT_BBOX_L_INF,
    strict_iou: float = DETECTOR_FIRST_STRICT_IOU,
    loose_iou: float = DETECTOR_FIRST_LOOSE_IOU,
) -> tuple[list[DetectorFirstLabelTransferRecord], dict[str, int]]:
    """Transfer labels only via exact crop SHA or strict geometry identity.

    Loose IoU overlap is counted as rejected and does not transfer a label.
    """

    labelled = [c for c in labelled_crops if c.sha256 in labels_by_crop_sha]
    by_sha = {c.sha256: c for c in labelled}
    transfers: list[DetectorFirstLabelTransferRecord] = []
    counts: dict[str, int] = Counter()
    seen_new: set[str] = set()

    for det in detector_records:
        if det.duplicate_of_region_id is not None:
            continue
        if det.crop_sha256 in by_sha and det.crop_sha256 in labels_by_crop_sha:
            label = labels_by_crop_sha[det.crop_sha256]
            transfers.append(
                DetectorFirstLabelTransferRecord(
                    new_crop_sha256=det.crop_sha256,
                    old_crop_sha256=det.crop_sha256,
                    method="exact_crop_sha256",
                    overlap_score=1.0,
                    label=label,
                    label_provenance="exact_crop_sha256",
                    created_at=_now(),
                )
            )
            counts[f"transfer_{label}"] += 1
            counts["exact_sha"] += 1
            seen_new.add(det.crop_sha256)
            continue

        best: tuple[float, CropRecord] | None = None
        for old in labelled:
            if old.sha256 in seen_new:
                continue
            if old.page_id != det.page_id and old.page_index != det.page_index:
                continue
            iou = bbox_iou(det.source_bbox, old.source_bbox)
            linf = bbox_l_inf(det.source_bbox, old.source_bbox)
            if linf <= strict_l_inf and iou >= strict_iou:
                score = iou
                if best is None or score > best[0]:
                    best = (score, old)
            elif iou >= loose_iou:
                counts["loose_overlap_rejected"] += 1

        if best is None:
            counts["unlabelled"] += 1
            continue
        old_crop = best[1]
        # Material crop-framing difference → leave unlabelled.
        crop_iou = bbox_iou(det.crop_bbox, old_crop.crop_bbox)
        if crop_iou < strict_iou:
            counts["framing_differs_unlabelled"] += 1
            continue
        label = labels_by_crop_sha[old_crop.sha256]
        transfers.append(
            DetectorFirstLabelTransferRecord(
                new_crop_sha256=det.crop_sha256,
                old_crop_sha256=old_crop.sha256,
                method="strict_geometry",
                overlap_score=float(best[0]),
                label=label,
                label_provenance="strict_geometry",
                created_at=_now(),
            )
        )
        counts[f"transfer_{label}"] += 1
        counts["strict_geometry"] += 1
        seen_new.add(det.crop_sha256)

    return transfers, dict(counts)


def classify_seed_coverage(
    seed_bbox: NormalisedBoundingBox,
    detector_bboxes: list[NormalisedBoundingBox],
    *,
    exact_iou: float = DETECTOR_FIRST_SEED_EXACT_IOU,
    contain_iou: float = DETECTOR_FIRST_SEED_CONTAIN_IOU,
    fragment_iou: float = DETECTOR_FIRST_SEED_FRAGMENT_IOU,
) -> SeedCoverageKind:
    """Classify how detector regions cover one handwriting seed geometry."""

    if not detector_bboxes:
        return "missed"
    ious = [bbox_iou(seed_bbox, d) for d in detector_bboxes]
    best = max(ious)
    if best >= exact_iou:
        return "exact" if best >= 0.98 else "near_exact"
    # Larger detector region containing the seed (IoU may be low when outer is large).
    for det in detector_bboxes:
        if (
            containment_ratio(seed_bbox, det) >= contain_iou
            and bbox_area_ratio(det, seed_bbox) >= 1.05
        ):
            return "contained"
    overlapping = [d for d, iou in zip(detector_bboxes, ious, strict=True) if iou >= fragment_iou]
    if len(overlapping) >= 2:
        return "fragmented"
    if best >= fragment_iou:
        return "fragmented"
    return "missed"


def bbox_area_ratio(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> float:
    ba = float(b.width * b.height)
    if ba <= 0.0:
        return 0.0
    return float((a.width * a.height) / ba)


def match_legacy_regions(
    detector_bboxes: list[NormalisedBoundingBox],
    legacy_bboxes: list[NormalisedBoundingBox],
    *,
    iou_threshold: float = DETECTOR_FIRST_COMPARE_IOU,
) -> dict[str, int]:
    """Greedy IoU matching between detector-first and legacy combined regions."""

    used_legacy: set[int] = set()
    matched = 0
    for det in detector_bboxes:
        best_j = -1
        best_iou = 0.0
        for j, leg in enumerate(legacy_bboxes):
            if j in used_legacy:
                continue
            score = bbox_iou(det, leg)
            if score > best_iou:
                best_iou = score
                best_j = j
        if best_j >= 0 and best_iou >= iou_threshold:
            used_legacy.add(best_j)
            matched += 1
    return {
        "detector_first_regions": len(detector_bboxes),
        "legacy_combined_regions": len(legacy_bboxes),
        "matched_regions": matched,
        "detector_first_only": len(detector_bboxes) - matched,
        "legacy_only": len(legacy_bboxes) - len(used_legacy),
    }


def build_aggregate_report(
    records: list[DetectorFirstRegionRecord],
    *,
    match_stats: dict[str, int] | None = None,
    label_transfer_counts: dict[str, int] | None = None,
    seed_coverage: dict[str, Any] | None = None,
    timing: dict[str, float] | None = None,
    recognition_equivalence: str | None = None,
) -> dict[str, Any]:
    """Safe aggregate report — no private IDs, paths, or OCR text."""

    canonical = [r for r in records if r.duplicate_of_region_id is None]
    status_counts = Counter(r.recognition_status for r in canonical)
    docs = {r.document_id for r in records}
    pages = {r.page_id for r in records}
    groups = {r.source_group_id for r in records}
    aspects = []
    areas = []
    for r in canonical:
        w, h = r.source_bbox.width, r.source_bbox.height
        areas.append(w * h)
        aspects.append(w / h if h > 0 else 0.0)
    report: dict[str, Any] = {
        "corpus_version": DETECTOR_FIRST_CORPUS_VERSION,
        "source_groups": len(groups),
        "documents": len(docs),
        "pages": len(pages),
        "detector_first_regions": len(records),
        "canonical_regions": len(canonical),
        "exact_duplicates": len(records) - len(canonical),
        "recognition_status_counts": dict(status_counts),
        "recognised": status_counts.get("recognised", 0),
        "empty_recognition": status_counts.get("empty", 0),
        "failed_recognition": status_counts.get("failed", 0),
        "low_confidence_recognition": status_counts.get("low_confidence", 0),
        "rejected_recognition": status_counts.get("rejected", 0),
        "not_run_recognition": status_counts.get("not_run", 0),
        "region_area_mean": (sum(areas) / len(areas)) if areas else 0.0,
        "region_aspect_mean": (sum(aspects) / len(aspects)) if aspects else 0.0,
    }
    if match_stats:
        report["legacy_comparison"] = match_stats
    if label_transfer_counts:
        report["label_transfer"] = {
            k: v
            for k, v in label_transfer_counts.items()
            if k.startswith("transfer_")
            or k
            in {
                "exact_sha",
                "strict_geometry",
                "loose_overlap_rejected",
                "framing_differs_unlabelled",
                "unlabelled",
            }
        }
    if seed_coverage:
        report["handwriting_seed_coverage"] = seed_coverage
    if timing:
        report["timing_seconds"] = timing
    if recognition_equivalence:
        report["recognition_equivalence_status"] = recognition_equivalence
    return report


def summarise_seed_coverage(
    seeds: list[HandwritingSeedRecord],
    page_detector_bboxes: dict[str, list[NormalisedBoundingBox]],
) -> dict[str, Any]:
    """Aggregate handwriting-seed detector coverage (no private IDs)."""

    active = [s for s in seeds if s.status == "active"]
    kinds: Counter[str] = Counter()
    by_category: dict[str, Counter[str]] = {}
    detected = 0
    for seed in active:
        boxes = page_detector_bboxes.get(seed.opaque_page_reference, [])
        kind = classify_seed_coverage(seed.geometry_normalized, boxes)
        kinds[kind] += 1
        if kind != "missed":
            detected += 1
        for cat in seed.categories:
            by_category.setdefault(cat, Counter())[kind] += 1

    def _recall(counter: Counter[str]) -> float:
        total = sum(counter.values())
        if total == 0:
            return 0.0
        return float((total - counter.get("missed", 0)) / total)

    category_recall = {
        cat: {
            "recall": _recall(ctr),
            "counts": dict(ctr),
        }
        for cat, ctr in sorted(by_category.items())
    }
    return {
        "handwriting_seed_total": len(active),
        "handwriting_seed_detected_count": detected,
        "handwriting_seed_detection_recall": (detected / len(active)) if active else 0.0,
        "coverage_kinds": dict(kinds),
        "fragmented_detections": kinds.get("fragmented", 0),
        "missed_detections": kinds.get("missed", 0),
        "cursive_detection_recall": category_recall.get("cursive", {}).get("recall", 0.0),
        "signature_detection_recall": category_recall.get("signature", {}).get("recall", 0.0),
        "by_category": category_recall,
    }


def write_private_manifests(
    private_root: Path,
    records: list[DetectorFirstRegionRecord],
    transfers: list[DetectorFirstLabelTransferRecord] | None = None,
) -> None:
    ensure_layout(private_root)
    write_jsonl_atomic(
        manifest_path(private_root, "detector-first-region-manifest.jsonl"),
        records,
    )
    if transfers is not None:
        write_jsonl_atomic(
            manifest_path(private_root, "detector-first-label-transfer.jsonl"),
            transfers,
        )


def write_private_aggregate(private_root: Path, report: dict[str, Any]) -> Path:
    ensure_layout(private_root)
    path = reports_dir(private_root) / "detector-first-corpus-aggregate.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_page_sources(private_root: Path) -> list[SourceRecord]:
    return read_jsonl(manifest_path(private_root, "source-manifest.jsonl"), SourceRecord)


def page_png_path(private_root: Path, page_id: str) -> Path:
    return private_root / "pages" / f"{page_id}.png"


def process_page_regions(
    *,
    private_root: Path,
    page: Image.Image,
    page_id: str,
    document_id: str,
    source_group_id: str,
    page_index: int,
    regions: list[DetectedTextRegion],
    recognise: RecogniseFn | None,
    low_thr: float,
    min_thr: float,
) -> list[DetectorFirstRegionRecord]:
    """Materialise crops for every detection; optionally recognise."""

    from io import BytesIO

    _ = page_index  # regions already carry page_index
    png_path = page_png_path(private_root, page_id)
    if png_path.is_file():
        buf_sha = sha256_file(png_path)
    else:
        _data_tmp, buf_sha, _ = png_bytes_and_hashes(page)
        del _data_tmp

    crop_dir = private_root / "detector-first" / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    built: list[tuple[DetectorFirstRegionRecord, bytes, Image.Image]] = []
    for region in regions:
        rel = f"detector-first/crops/{region.region_id}.png"
        record, data = build_region_crop(
            page=page,
            region=region,
            page_id=page_id,
            document_id=document_id,
            source_group_id=source_group_id,
            page_render_sha256=buf_sha,
            crop_relpath=rel,
        )
        crop_img = Image.open(BytesIO(data)).convert("RGB")
        built.append((record, data, crop_img))

    if recognise is not None and built:
        payloads = [(r.region_id, img) for r, _data, img in built]
        results = recognise(payloads)
        by_id = {r.region_id: r for r in results}
        updated: list[DetectorFirstRegionRecord] = []
        for record, data, _img in built:
            path = private_root / record.crop_relpath
            if not path.is_file() or sha256_file(path) != record.crop_sha256:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            rec = by_id.get(record.region_id)
            if rec is not None:
                record = apply_recognition_metadata(record, rec, low_thr=low_thr, min_thr=min_thr)
            updated.append(record)
        return updated

    out: list[DetectorFirstRegionRecord] = []
    for record, data, _img in built:
        path = private_root / record.crop_relpath
        if not path.is_file() or sha256_file(path) != record.crop_sha256:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        out.append(record)
    return out


def measure_regions_in_memory(
    *,
    page: Image.Image,
    page_id: str,
    document_id: str,
    source_group_id: str,
    page_index: int,
    regions: list[DetectedTextRegion],
    recognise: RecogniseFn | None,
    low_thr: float,
    min_thr: float,
    page_render_sha256: str = "0" * 64,
) -> list[DetectorFirstRegionRecord]:
    """Build region records and optionally recognise without writing crops.

    Used by Task C1 calibration corpus/sample runs so Task C0 v1 artefacts are
    not overwritten.
    """

    from io import BytesIO

    _ = page_index
    built: list[tuple[DetectorFirstRegionRecord, Image.Image]] = []
    for region in regions:
        rel = f"detector-first/calib-ephemeral/{region.region_id}.png"
        record, data = build_region_crop(
            page=page,
            region=region,
            page_id=page_id,
            document_id=document_id,
            source_group_id=source_group_id,
            page_render_sha256=page_render_sha256,
            crop_relpath=rel,
        )
        crop_img = Image.open(BytesIO(data)).convert("RGB")
        built.append((record, crop_img))

    if recognise is None or not built:
        return [r for r, _ in built]

    payloads = [(r.region_id, img) for r, img in built]
    results = recognise(payloads)
    by_id = {r.region_id: r for r in results}
    updated: list[DetectorFirstRegionRecord] = []
    for record, _img in built:
        rec = by_id.get(record.region_id)
        if rec is not None:
            record = apply_recognition_metadata(record, rec, low_thr=low_thr, min_thr=min_thr)
        updated.append(record)
    return updated
