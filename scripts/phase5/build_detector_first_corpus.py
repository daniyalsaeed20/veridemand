"""Offline detector-first private corpus builder (Phase 5 Task C0).

Runs Paddle text detection separately from recognition against approved
private page renders. Never logs OCR text or private identifiers.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _ensure_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _aggregate_only(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip any accidental private keys from printed aggregates."""

    forbidden = ("path", "relpath", "page_id", "document_id", "region_id", "crop_id", "text")
    out: dict[str, Any] = {}
    for key, value in payload.items():
        key_l = key.lower()
        if any(f in key_l for f in forbidden):
            continue
        if isinstance(value, dict):
            out[key] = _aggregate_only(value)
        else:
            out[key] = value
    return out


def build_corpus(
    *,
    private_root: Path,
    run_recognition: bool,
    compare_legacy: bool,
    max_pages: int | None,
) -> dict[str, Any]:
    from backend.app.datasets.phase5.detector_first import (
        build_aggregate_report,
        load_page_sources,
        mark_exact_duplicates,
        match_legacy_regions,
        page_png_path,
        process_page_regions,
        summarise_seed_coverage,
        transfer_labels,
        write_private_aggregate,
        write_private_manifests,
    )
    from backend.app.datasets.phase5.jsonl_io import read_jsonl
    from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, reports_dir
    from backend.app.datasets.phase5.schemas import (
        CropRecord,
        DocumentRecord,
        HandwritingSeedRecord,
        ResolvedLabelRecord,
    )
    from backend.app.extraction.visual.models import OcrRuntimeConfig
    from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter
    from backend.app.settings.config import Settings
    from PIL import Image

    ensure_layout(private_root)
    settings = Settings()
    config = OcrRuntimeConfig(
        ocr_detection_model_name=settings.ocr_detection_model_name,
        ocr_recognition_model_name=settings.ocr_recognition_model_name,
        ocr_model_root=str(settings.ocr_model_root),
        ocr_device=settings.ocr_device,
        ocr_engine=settings.ocr_engine,
        ocr_cpu_threads=settings.ocr_cpu_threads,
        ocr_recognition_batch_size=settings.ocr_recognition_batch_size,
        ocr_text_det_limit_side_len=settings.ocr_text_det_limit_side_len,
        ocr_min_recognition_score=settings.ocr_min_recognition_score,
        ocr_low_confidence_score=settings.ocr_low_confidence_score,
    )
    adapter = PaddleOcrAdapter(config)
    t0 = time.perf_counter()
    adapter.load_detect_first_modules()
    detect_load_s = time.perf_counter() - t0

    legacy_adapter: PaddleOcrAdapter | None = None
    if compare_legacy:
        legacy_adapter = PaddleOcrAdapter(config)
        t_leg = time.perf_counter()
        legacy_adapter.load()
        legacy_load_s = time.perf_counter() - t_leg
    else:
        legacy_load_s = 0.0

    docs = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }
    sources = load_page_sources(private_root)
    if max_pages is not None:
        sources = sources[: max(0, max_pages)]

    all_records = []
    match_accum = {
        "detector_first_regions": 0,
        "legacy_combined_regions": 0,
        "matched_regions": 0,
        "detector_first_only": 0,
        "legacy_only": 0,
    }
    page_detector_bboxes: dict[str, list[Any]] = defaultdict(list)
    detect_s = 0.0
    recognise_s = 0.0
    legacy_s = 0.0
    pages_processed = 0
    pages_missing = 0

    low_thr = float(settings.ocr_low_confidence_score)
    min_thr = float(settings.ocr_min_recognition_score)

    def _recognise(crops: list[tuple[str, Any]]) -> list[Any]:
        nonlocal recognise_s
        t = time.perf_counter()
        out = adapter.recognise_text_crops(crops)
        recognise_s += time.perf_counter() - t
        return out

    for source in sources:
        png = page_png_path(private_root, source.page_id)
        if not png.is_file():
            pages_missing += 1
            continue
        doc = docs.get(source.document_id)
        if doc is None:
            pages_missing += 1
            continue
        with Image.open(png) as img:
            page = img.convert("RGB")
            t = time.perf_counter()
            regions = adapter.detect_text(page, page_index=source.page_index)
            detect_s += time.perf_counter() - t
            for region in regions:
                from backend.app.datasets.phase5.geometry_match import bbox_from_tuple

                page_detector_bboxes[source.page_id].append(bbox_from_tuple(region.bbox_norm))

            if compare_legacy and legacy_adapter is not None:
                t = time.perf_counter()
                legacy_lines = legacy_adapter.recognise(page)
                legacy_s += time.perf_counter() - t
                from backend.app.extraction.visual.coordinates import map_pixel_polygon

                legacy_boxes = []
                w_px, h_px = page.size
                for line in legacy_lines:
                    try:
                        mapped = map_pixel_polygon(
                            line.polygon_px, width_pixels=w_px, height_pixels=h_px
                        )
                        legacy_boxes.append(mapped.bbox)
                    except Exception:
                        continue
                det_boxes = [bbox_from_tuple(r.bbox_norm) for r in regions]
                stats = match_legacy_regions(det_boxes, legacy_boxes)
                for key, value in stats.items():
                    match_accum[key] = match_accum.get(key, 0) + value

            page_records = process_page_regions(
                private_root=private_root,
                page=page,
                page_id=source.page_id,
                document_id=source.document_id,
                source_group_id=source.source_group_id,
                page_index=source.page_index,
                regions=regions,
                recognise=_recognise if run_recognition else None,
                low_thr=low_thr,
                min_thr=min_thr,
            )
            all_records.extend(page_records)
            pages_processed += 1

    all_records = mark_exact_duplicates(all_records)

    labels_by_sha: dict[str, str] = {}
    resolved_path = manifest_path(private_root, "resolved-labels.jsonl")
    if resolved_path.is_file():
        for row in read_jsonl(resolved_path, ResolvedLabelRecord):
            if row.label and row.crop_sha256:
                labels_by_sha[row.crop_sha256] = row.label
    crops = read_jsonl(manifest_path(private_root, "crop-manifest.jsonl"), CropRecord)
    transfers, transfer_counts = transfer_labels(
        detector_records=all_records,
        labelled_crops=crops,
        labels_by_crop_sha=labels_by_sha,
    )

    seeds: list[HandwritingSeedRecord] = []
    seed_path = manifest_path(private_root, "handwriting-seed-records.jsonl")
    if seed_path.is_file():
        seeds = read_jsonl(seed_path, HandwritingSeedRecord)
    seed_coverage = summarise_seed_coverage(seeds, page_detector_bboxes)

    # Equivalence heuristic for Task C0 (aggregates only).
    recognised = sum(1 for r in all_records if r.recognition_status == "recognised")
    empty = sum(1 for r in all_records if r.recognition_status == "empty")
    failed = sum(1 for r in all_records if r.recognition_status == "failed")
    matched = match_accum.get("matched_regions", 0)

    if not run_recognition:
        equivalence = "not_evaluated_recognition_skipped"
    elif failed > max(1, recognised // 5) or (
        compare_legacy and matched == 0 and match_accum.get("detector_first_regions", 0) > 0
    ):
        equivalence = "requires_adapter_correction"
    else:
        equivalence = "acceptable_for_next_integration_task"

    report = build_aggregate_report(
        all_records,
        match_stats=match_accum if compare_legacy else None,
        label_transfer_counts=transfer_counts,
        seed_coverage=seed_coverage,
        timing={
            "detect_first_load": detect_load_s,
            "legacy_load": legacy_load_s,
            "detect": detect_s,
            "recognise": recognise_s,
            "legacy_predict": legacy_s,
        },
        recognition_equivalence=equivalence,
    )
    report["pages_processed"] = pages_processed
    report["pages_missing_render"] = pages_missing
    report["empty_vs_recognised_ratio"] = (empty / recognised) if recognised else None

    sample_compare = bool(compare_legacy and max_pages is not None)
    if sample_compare:
        # Sample comparisons must not overwrite full-corpus manifests/aggregates.
        path = reports_dir(private_root) / "detector-first-compare-sample-aggregate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        write_private_manifests(private_root, all_records, transfers)
        write_private_aggregate(private_root, report)
    return report


def cmd_coverage(private_root: Path) -> dict[str, Any]:
    from backend.app.datasets.phase5.detector_first import summarise_seed_coverage
    from backend.app.datasets.phase5.detector_first_schemas import DetectorFirstRegionRecord
    from backend.app.datasets.phase5.jsonl_io import read_jsonl
    from backend.app.datasets.phase5.paths import manifest_path
    from backend.app.datasets.phase5.schemas import HandwritingSeedRecord

    records = read_jsonl(
        manifest_path(private_root, "detector-first-region-manifest.jsonl"),
        DetectorFirstRegionRecord,
    )
    by_page: dict[str, list[Any]] = defaultdict(list)
    for record in records:
        if record.duplicate_of_region_id is None:
            by_page[record.page_id].append(record.source_bbox)
    seeds = read_jsonl(
        manifest_path(private_root, "handwriting-seed-records.jsonl"),
        HandwritingSeedRecord,
    )
    # Map seed opaque_page_reference → page_id when they match.
    return summarise_seed_coverage(seeds, by_page)


def main(argv: list[str] | None = None) -> int:
    _ensure_path()
    parser = argparse.ArgumentParser(description="Phase 5 detector-first corpus tooling")
    parser.add_argument(
        "command",
        choices=("build", "compare", "coverage"),
        help="build|compare|coverage",
    )
    parser.add_argument("--root", type=str, default=None, help="Private phase5 root")
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument(
        "--skip-recognition",
        action="store_true",
        help="Detect + crop only (retain recognition_status=not_run)",
    )
    args = parser.parse_args(argv)

    from backend.app.datasets.phase5.paths import default_private_root

    private_root = Path(args.root) if args.root else default_private_root()
    if args.command == "coverage":
        report = cmd_coverage(private_root)
        print(json.dumps(_aggregate_only(report), indent=2, sort_keys=True))
        return 0

    compare = args.command == "compare"
    report = build_corpus(
        private_root=private_root,
        run_recognition=not args.skip_recognition,
        compare_legacy=compare,
        max_pages=args.max_pages,
    )
    print(json.dumps(_aggregate_only(report), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
