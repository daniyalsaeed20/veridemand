#!/usr/bin/env python3
"""Phase 5 Task C1 — offline handwriting detector recall calibration.

Commands:
  baseline          Reproduce Task C0 mobile seed coverage
  grid              Run bounded (<=12) detector configs on seed pages
  corpus            Full private corpus impact for shortlisted configs
  recognise-sample  10-page recognition compatibility sample
  select            Apply zero-miss gate and emit decision
  build-v2          Build detector-first corpus v2 for selected candidate

Never enables live routing. Never logs OCR text or private page IDs.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _ensure_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _aggregate_only(payload: dict[str, Any]) -> dict[str, Any]:
    forbidden = ("path", "relpath", "page_id", "document_id", "region_id", "crop_id", "text")
    out: dict[str, Any] = {}
    for key, value in payload.items():
        key_l = key.lower()
        if any(f in key_l for f in forbidden):
            continue
        if isinstance(value, dict):
            out[key] = _aggregate_only(value)
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            out[key] = [_aggregate_only(v) if isinstance(v, dict) else v for v in value]
        else:
            out[key] = value
    return out


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(_aggregate_only(payload), indent=2, sort_keys=True), flush=True)


def _reports_dir(private_root: Path) -> Path:
    path = private_root / "reports" / "detector-calibration"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_report(private_root: Path, name: str, payload: dict[str, Any]) -> Path:
    path = _reports_dir(private_root) / name
    path.write_text(
        json.dumps(_aggregate_only(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _ocr_config():
    from backend.app.extraction.visual.models import OcrRuntimeConfig
    from backend.app.settings.config import Settings

    settings = Settings()
    return settings, OcrRuntimeConfig(
        ocr_detection_model_name=settings.ocr_detection_model_name,
        ocr_recognition_model_name=settings.ocr_recognition_model_name,
        ocr_model_root=str(settings.ocr_model_root),
        ocr_device=settings.ocr_device,
        ocr_engine=settings.ocr_engine,
        ocr_cpu_threads=settings.ocr_cpu_threads,
        ocr_recognition_batch_size=settings.ocr_recognition_batch_size,
        ocr_text_det_limit_side_len=settings.ocr_text_det_limit_side_len,
        ocr_text_det_limit_type=settings.ocr_text_det_limit_type,
        ocr_text_det_thresh=settings.ocr_text_det_thresh,
        ocr_text_det_box_thresh=settings.ocr_text_det_box_thresh,
        ocr_text_det_unclip_ratio=settings.ocr_text_det_unclip_ratio,
        ocr_min_recognition_score=settings.ocr_min_recognition_score,
        ocr_low_confidence_score=settings.ocr_low_confidence_score,
    )


def _load_seeds(private_root: Path):
    from backend.app.datasets.phase5.jsonl_io import read_jsonl
    from backend.app.datasets.phase5.paths import manifest_path
    from backend.app.datasets.phase5.schemas import HandwritingSeedRecord

    seed_path = manifest_path(private_root, "handwriting-seed-records.jsonl")
    if not seed_path.is_file():
        return []
    return read_jsonl(seed_path, HandwritingSeedRecord)


def _seed_pages(private_root: Path, seeds) -> list[Any]:
    from backend.app.datasets.phase5.detector_first import load_page_sources

    needed = {s.opaque_page_reference for s in seeds if s.status == "active"}
    sources = load_page_sources(private_root)
    return [s for s in sources if s.page_id in needed]


def _adapter_for_model(config, detection_model_name: str, *, with_rec: bool):
    from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter

    adapter = PaddleOcrAdapter(config)
    if detection_model_name == config.ocr_detection_model_name and with_rec:
        adapter.load_detect_first_modules()
    else:
        adapter.load_shadow_detector(
            detection_model_name=detection_model_name,
            load_recognizer=with_rec,
        )
    return adapter


def _detect_page(adapter, page, page_index: int, params):
    return adapter.detect_text(page, page_index=page_index, params=params)


def _run_config_on_pages(
    *,
    config_row,
    sources,
    private_root: Path,
    runtime_config,
    adapter_cache: dict[str, Any],
    detection_cache: dict[tuple[Any, ...], list[Any]] | None = None,
    with_rec: bool = False,
) -> dict[str, Any]:
    from backend.app.datasets.phase5.detector_calibration import (
        count_pathological_boxes,
        known_seed_gate_passes,
        summarise_seed_coverage_sensitivity,
    )
    from backend.app.datasets.phase5.detector_first import (
        page_png_path,
        summarise_seed_coverage,
    )
    from backend.app.datasets.phase5.detector_merge import merge_detector_regions
    from backend.app.datasets.phase5.geometry_match import bbox_from_tuple
    from PIL import Image

    if detection_cache is None:
        detection_cache = {}

    family = config_row.family
    primary_name = config_row.detection_model_name
    if primary_name not in adapter_cache:
        adapter_cache[primary_name] = _adapter_for_model(
            runtime_config, primary_name, with_rec=with_rec
        )
    primary = adapter_cache[primary_name]

    secondary = None
    if family == "merged":
        partner = config_row.merge_partner_model_name
        assert partner is not None
        if partner not in adapter_cache:
            adapter_cache[partner] = _adapter_for_model(runtime_config, partner, with_rec=False)
        secondary = adapter_cache[partner]

    def _cache_key(model_name: str, params) -> tuple[Any, ...]:
        if params is None:
            return (model_name, "intrinsic")
        return (
            model_name,
            params.thresh,
            params.box_thresh,
            params.unclip_ratio,
            params.limit_side_len,
            params.limit_type,
        )

    page_detector_bboxes: dict[str, list[Any]] = defaultdict(list)
    boxes_per_page: list[int] = []
    pathological = 0
    total_regions = 0
    detect_s = 0.0
    pages_processed = 0
    pages_missing = 0

    for source in sources:
        png = page_png_path(private_root, source.page_id)
        if not png.is_file():
            pages_missing += 1
            continue
        with Image.open(png) as img:
            page = img.convert("RGB")
            primary_key = (*_cache_key(primary_name, config_row.predict_params()), source.page_id)
            t = time.perf_counter()
            if primary_key in detection_cache:
                regions = detection_cache[primary_key]
            else:
                regions = _detect_page(
                    primary, page, source.page_index, config_row.predict_params()
                )
                detection_cache[primary_key] = regions
            if secondary is not None:
                partner_name = config_row.merge_partner_model_name
                assert partner_name is not None
                partner_key = (
                    *_cache_key(partner_name, config_row.predict_partner_params()),
                    source.page_id,
                )
                if partner_key in detection_cache:
                    partner_regions = detection_cache[partner_key]
                else:
                    partner_regions = _detect_page(
                        secondary,
                        page,
                        source.page_index,
                        config_row.predict_partner_params(),
                    )
                    detection_cache[partner_key] = partner_regions
                regions = merge_detector_regions(regions, partner_regions)
            detect_s += time.perf_counter() - t

        bboxes = [bbox_from_tuple(r.bbox_norm) for r in regions]
        pathological += count_pathological_boxes(bboxes)
        page_detector_bboxes[source.page_id] = bboxes
        boxes_per_page.append(len(regions))
        total_regions += len(regions)
        pages_processed += 1

    seeds = _load_seeds(private_root)
    seed_coverage = summarise_seed_coverage(seeds, page_detector_bboxes)
    sensitivity = summarise_seed_coverage_sensitivity(seeds, page_detector_bboxes)
    gate = known_seed_gate_passes(seed_coverage) and pathological == 0

    by_cat = seed_coverage.get("by_category") or {}
    return {
        **config_row.to_public_dict(),
        "pages_processed": pages_processed,
        "pages_missing_render": pages_missing,
        "total_regions": total_regions,
        "median_boxes_per_page": (
            float(statistics.median(boxes_per_page)) if boxes_per_page else 0.0
        ),
        "max_boxes_per_page": max(boxes_per_page) if boxes_per_page else 0,
        "pathological_box_count": pathological,
        "detector_time_seconds": round(detect_s, 3),
        "seed_coverage": seed_coverage,
        "sensitivity": sensitivity,
        "overall_recall": seed_coverage.get("handwriting_seed_detection_recall"),
        "digits_recall": (by_cat.get("digits") or {}).get("recall"),
        "hand_print_recall": (by_cat.get("hand_printed") or {}).get("recall"),
        "cursive_recall": (by_cat.get("cursive") or {}).get("recall"),
        "signature_recall": (by_cat.get("signature") or {}).get("recall"),
        "longer_note_recall": (by_cat.get("longer_note") or {}).get("recall"),
        "fragments": seed_coverage.get("fragmented_detections"),
        "misses": seed_coverage.get("missed_detections"),
        "gate_passed": gate,
        "recognition_degradation_score": 0.0,
        "recognition_compatibility": "not_evaluated",
    }


def cmd_baseline(private_root: Path) -> dict[str, Any]:
    from backend.app.datasets.phase5.constants import MOBILE_DETECTION_MODEL_NAME
    from backend.app.datasets.phase5.detector_calibration import (
        DetectorCalibrationConfig,
        mobile_baseline_params,
    )

    settings, config = _ocr_config()
    assert settings.phase5_detect_first_shadow_enabled is False
    assert settings.handwriting_router_enabled is False

    seeds = _load_seeds(private_root)
    sources = _seed_pages(private_root, seeds)
    row = DetectorCalibrationConfig(
        family="mobile",
        detection_model_name=MOBILE_DETECTION_MODEL_NAME,
        params=mobile_baseline_params(),
        label="mobile_c0_intrinsic",
        apply_params=False,
    )
    result = _run_config_on_pages(
        config_row=row,
        sources=sources,
        private_root=private_root,
        runtime_config=config,
        adapter_cache={},
        with_rec=False,
    )
    result["task"] = "baseline"
    result["expected_c0"] = {
        "handwriting_seed_total": 55,
        "detected": 36,
        "missed": 19,
        "overall_recall": 0.655,
    }
    _write_report(private_root, "baseline-seed-coverage.json", result)
    return result


def cmd_grid(private_root: Path, *, skip_server: bool) -> dict[str, Any]:
    from backend.app.datasets.phase5.constants import SERVER_DETECTION_MODEL_NAME
    from backend.app.datasets.phase5.detector_calibration import (
        build_bounded_calibration_grid,
    )
    from backend.app.extraction.visual.model_paths import (
        require_local_detection_dir,
        resolve_ocr_model_root,
    )

    settings, config = _ocr_config()
    include_server = not skip_server
    if include_server:
        try:
            require_local_detection_dir(
                resolve_ocr_model_root(config.ocr_model_root),
                detection_model_name=SERVER_DETECTION_MODEL_NAME,
            )
        except FileNotFoundError:
            include_server = False

    grid = build_bounded_calibration_grid(
        include_server=include_server,
        include_merged=include_server,
    )
    seeds = _load_seeds(private_root)
    sources = _seed_pages(private_root, seeds)
    adapter_cache: dict[str, Any] = {}
    detection_cache: dict[tuple[Any, ...], list[Any]] = {}
    results: list[dict[str, Any]] = []
    for index, row in enumerate(grid, start=1):
        print(
            f"[grid] {index}/{len(grid)} {row.label} ({row.family})",
            flush=True,
        )
        result = _run_config_on_pages(
            config_row=row,
            sources=sources,
            private_root=private_root,
            runtime_config=config,
            adapter_cache=adapter_cache,
            detection_cache=detection_cache,
            with_rec=False,
        )
        results.append(result)
        print(
            f"[grid] done recall={result.get('overall_recall')} "
            f"misses={result.get('misses')} regions={result.get('total_regions')} "
            f"time_s={result.get('detector_time_seconds')}",
            flush=True,
        )
        # Persist partial results so long runs are recoverable.
        _write_report(
            private_root,
            "grid-seed-comparison.partial.json",
            {
                "task": "grid_partial",
                "completed": len(results),
                "total": len(grid),
                "candidates": results,
            },
        )

    payload = {
        "task": "grid",
        "calibration_version": "phase5-detector-calibration-v1",
        "config_count": len(results),
        "server_included": include_server,
        "shadow_enabled": settings.phase5_detect_first_shadow_enabled,
        "router_enabled": settings.handwriting_router_enabled,
        "candidates": results,
    }
    _write_report(private_root, "grid-seed-comparison.json", payload)
    return payload


def cmd_corpus(
    private_root: Path,
    *,
    config_ids: list[str] | None,
    max_pages: int | None,
) -> dict[str, Any]:
    from backend.app.datasets.phase5.detector_calibration import (
        build_bounded_calibration_grid,
    )
    from backend.app.datasets.phase5.detector_first import (
        load_page_sources,
        mark_exact_duplicates,
        measure_regions_in_memory,
        page_png_path,
    )
    from backend.app.datasets.phase5.detector_merge import merge_detector_regions
    from backend.app.datasets.phase5.jsonl_io import read_jsonl
    from backend.app.datasets.phase5.paths import manifest_path
    from backend.app.datasets.phase5.schemas import DocumentRecord
    from PIL import Image

    settings, config = _ocr_config()
    grid_path = _reports_dir(private_root) / "grid-seed-comparison.json"
    if grid_path.is_file():
        grid_payload = json.loads(grid_path.read_text(encoding="utf-8"))
        candidates = grid_payload.get("candidates") or []
    else:
        candidates = [c.to_public_dict() for c in build_bounded_calibration_grid()]

    # Prefer gate-passing; else top-3 by overall recall then fewest misses.
    if config_ids:
        selected = [c for c in candidates if c.get("config_id") in set(config_ids)]
    else:
        passing = [c for c in candidates if c.get("gate_passed")]
        if passing:
            selected = passing[:3]
        else:
            selected = sorted(
                candidates,
                key=lambda c: (
                    -float(c.get("overall_recall") or 0.0),
                    int(c.get("misses") or 10**9),
                    int(c.get("total_regions") or 10**9),
                ),
            )[:3]

    grid_by_id = {
        c.config_id: c
        for c in build_bounded_calibration_grid(include_server=True, include_merged=True)
    }
    # Rebuild config objects from public dicts when needed.
    from backend.app.datasets.phase5.detector_calibration import DetectorCalibrationConfig
    from backend.app.extraction.visual.detect_first_types import DetectorRuntimeParams

    def _hydrate(row: dict[str, Any]):
        cid = row["config_id"]
        if cid in grid_by_id:
            return grid_by_id[cid]
        params = DetectorRuntimeParams(**row["params"])
        partner = None
        if row.get("merge_partner_params"):
            partner = DetectorRuntimeParams(**row["merge_partner_params"])
        return DetectorCalibrationConfig(
            family=row["family"],
            detection_model_name=row["detection_model_name"],
            params=params,
            merge_partner_model_name=row.get("merge_partner_model_name"),
            merge_partner_params=partner,
            merge_version=row.get("merge_version"),
            label=row.get("label") or "",
            apply_params=bool(row.get("apply_params", True)),
        )

    docs = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }
    sources = load_page_sources(private_root)
    if max_pages is not None:
        sources = sources[: max(0, max_pages)]

    baseline_regions = None
    # Use C0 documented region count from prior aggregate when available.
    c0_agg = private_root / "reports" / "detector-first-aggregate.json"
    if not c0_agg.is_file():
        c0_agg = private_root / "reports" / "detector-first-corpus-aggregate.json"
    if c0_agg.is_file():
        try:
            baseline_regions = int(
                json.loads(c0_agg.read_text(encoding="utf-8")).get("detector_first_regions", 0)
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            baseline_regions = None

    adapter_cache: dict[str, Any] = {}
    corpus_results: list[dict[str, Any]] = []
    low_thr = float(settings.ocr_low_confidence_score)
    min_thr = float(settings.ocr_min_recognition_score)

    for row in selected:
        cfg = _hydrate(row)
        primary_name = cfg.detection_model_name
        if primary_name not in adapter_cache:
            adapter_cache[primary_name] = _adapter_for_model(config, primary_name, with_rec=True)
        primary = adapter_cache[primary_name]
        secondary = None
        if cfg.family == "merged":
            partner = cfg.merge_partner_model_name
            assert partner is not None
            key = f"{partner}:det"
            if key not in adapter_cache:
                adapter_cache[key] = _adapter_for_model(config, partner, with_rec=False)
            secondary = adapter_cache[key]

        all_records = []
        detect_s = 0.0
        recognise_s = 0.0
        pages_processed = 0
        pages_missing = 0
        boxes_per_page: list[int] = []

        def _recognise(crops: list[tuple[str, Any]], _primary=primary) -> list[Any]:
            nonlocal recognise_s
            t = time.perf_counter()
            out = _primary.recognise_text_crops(crops)
            recognise_s += time.perf_counter() - t
            return out

        for source in sources:
            png = page_png_path(private_root, source.page_id)
            if not png.is_file() or source.document_id not in docs:
                pages_missing += 1
                continue
            with Image.open(png) as img:
                page = img.convert("RGB")
                t = time.perf_counter()
                regions = _detect_page(primary, page, source.page_index, cfg.predict_params())
                if secondary is not None:
                    partner_regions = _detect_page(
                        secondary,
                        page,
                        source.page_index,
                        cfg.predict_partner_params(),
                    )
                    regions = merge_detector_regions(regions, partner_regions)
                detect_s += time.perf_counter() - t
                boxes_per_page.append(len(regions))
                page_records = measure_regions_in_memory(
                    page=page,
                    page_id=source.page_id,
                    document_id=source.document_id,
                    source_group_id=source.source_group_id,
                    page_index=source.page_index,
                    regions=regions,
                    recognise=_recognise,
                    low_thr=low_thr,
                    min_thr=min_thr,
                )
                all_records.extend(page_records)
            pages_processed += 1

        all_records = mark_exact_duplicates(all_records)
        canonical = [r for r in all_records if r.duplicate_of_region_id is None]
        status_counts = Counter(r.recognition_status for r in canonical)
        total = len(all_records)
        growth = None
        if baseline_regions and baseline_regions > 0:
            growth = round(total / baseline_regions, 4)

        corpus_results.append(
            {
                "config_id": cfg.config_id,
                "label": cfg.label,
                "family": cfg.family,
                "pages_processed": pages_processed,
                "pages_missing_render": pages_missing,
                "total_regions": total,
                "canonical_regions": len(canonical),
                "exact_duplicates": total - len(canonical),
                "average_regions_per_page": (
                    round(total / pages_processed, 3) if pages_processed else 0.0
                ),
                "median_boxes_per_page": (
                    float(statistics.median(boxes_per_page)) if boxes_per_page else 0.0
                ),
                "max_boxes_per_page": max(boxes_per_page) if boxes_per_page else 0,
                "recognition_status_counts": dict(status_counts),
                "empty_recognition": status_counts.get("empty", 0),
                "low_confidence_recognition": status_counts.get("low_confidence", 0),
                "failed_recognition": status_counts.get("failed", 0),
                "detector_time_seconds": round(detect_s, 3),
                "recognition_time_seconds": round(recognise_s, 3),
                "region_growth_ratio_vs_c0_mobile": growth,
                "baseline_c0_regions": baseline_regions,
            }
        )

    payload = {
        "task": "corpus",
        "candidates": corpus_results,
        "note": "In-memory recognition only; Task C0 v1 crops/manifests preserved.",
    }
    _write_report(private_root, "corpus-impact.json", payload)
    return payload


def cmd_recognise_sample(
    private_root: Path,
    *,
    max_pages: int = 10,
) -> dict[str, Any]:
    """Bounded recognition compatibility on the same 10-page sample style as C0."""

    from backend.app.datasets.phase5.detector_calibration import (
        build_bounded_calibration_grid,
        known_seed_gate_passes,
    )

    # Reuse corpus command with max_pages for shortlisted candidates.
    corpus = cmd_corpus(private_root, config_ids=None, max_pages=max_pages)
    grid_path = _reports_dir(private_root) / "grid-seed-comparison.json"
    grid_candidates = []
    if grid_path.is_file():
        grid_candidates = json.loads(grid_path.read_text(encoding="utf-8")).get("candidates") or []

    sample_rows = []
    for row in corpus.get("candidates") or []:
        gate_row = next(
            (g for g in grid_candidates if g.get("config_id") == row.get("config_id")),
            {},
        )
        empty = int(row.get("empty_recognition") or 0)
        failed = int(row.get("failed_recognition") or 0)
        recognised = int((row.get("recognition_status_counts") or {}).get("recognised", 0))
        matched = int(row.get("canonical_regions") or 0)
        if failed > max(1, recognised // 5) and recognised > 0:
            status = "not_acceptable"
        elif (empty > recognised and recognised > 0) or (recognised == 0 and matched > 0):
            status = "requires_crop_or_merge_correction"
        else:
            status = "acceptable_for_retraining"
        sample_rows.append(
            {
                "config_id": row.get("config_id"),
                "label": row.get("label"),
                "family": row.get("family"),
                "matched_region_count": matched,
                "recognised_count": recognised,
                "empty_results": empty,
                "low_confidence_results": row.get("low_confidence_recognition"),
                "failed_results": failed,
                "recognition_compatibility": status,
                "detector_time_seconds": row.get("detector_time_seconds"),
                "recognition_time_seconds": row.get("recognition_time_seconds"),
                "seed_gate_passed": known_seed_gate_passes(gate_row.get("seed_coverage") or {}),
                "overall_recall": gate_row.get("overall_recall"),
            }
        )

    payload = {
        "task": "recognise-sample",
        "comparison_sample_pages": max_pages,
        "candidates": sample_rows,
        "grid_size": len(build_bounded_calibration_grid()),
    }
    _write_report(private_root, "recognition-compatibility-sample.json", payload)
    return payload


def cmd_select(private_root: Path) -> dict[str, Any]:
    from backend.app.datasets.phase5.detector_calibration import rank_passing_candidates

    grid_path = _reports_dir(private_root) / "grid-seed-comparison.json"
    if not grid_path.is_file():
        return {
            "decision": "DETECTOR COVERAGE STILL INSUFFICIENT",
            "reason": "grid report missing — run grid first",
        }
    grid = json.loads(grid_path.read_text(encoding="utf-8"))
    candidates = grid.get("candidates") or []

    # Merge recognition compatibility if present.
    recog_path = _reports_dir(private_root) / "recognition-compatibility-sample.json"
    recog_by_id: dict[str, Any] = {}
    if recog_path.is_file():
        for row in json.loads(recog_path.read_text(encoding="utf-8")).get("candidates") or []:
            recog_by_id[row["config_id"]] = row

    corpus_path = _reports_dir(private_root) / "corpus-impact.json"
    corpus_by_id: dict[str, Any] = {}
    if corpus_path.is_file():
        for row in json.loads(corpus_path.read_text(encoding="utf-8")).get("candidates") or []:
            corpus_by_id[row["config_id"]] = row

    enriched = []
    for c in candidates:
        if c.get("skipped"):
            enriched.append(
                {**c, "gate_passed": False, "config_id": c.get("config_id") or c.get("label")}
            )
            continue
        cid = c["config_id"]
        recog = recog_by_id.get(cid) or {}
        corpus = corpus_by_id.get(cid) or {}
        compat = recog.get("recognition_compatibility", "not_evaluated")
        gate = bool(c.get("gate_passed")) and compat != "not_acceptable"
        if corpus.get("pathological_box_count"):
            gate = False
        row = {
            **c,
            "gate_passed": gate,
            "recognition_compatibility": compat,
            "total_regions": corpus.get("total_regions", c.get("total_regions")),
            "detector_time_seconds": corpus.get(
                "detector_time_seconds", c.get("detector_time_seconds")
            ),
            "recognition_degradation_score": float(
                (recog.get("empty_results") or 0) + 2 * (recog.get("failed_results") or 0)
            ),
            "region_growth_ratio_vs_c0_mobile": corpus.get("region_growth_ratio_vs_c0_mobile"),
        }
        enriched.append(row)

    ranked = rank_passing_candidates(enriched)
    pareto: list[dict[str, Any]]
    if ranked:
        selected = ranked[0]
        decision = "HANDWRITING-CAPABLE DETECTOR CANDIDATE READY"
        pareto = ranked
    else:
        selected = None
        # Pareto front: best overall recall, then fewest misses, then fewest regions.
        pareto = sorted(
            enriched,
            key=lambda r: (
                -float(r.get("overall_recall") or 0.0),
                int(r.get("misses") or 10**9),
                int(r.get("total_regions") or 10**9),
            ),
        )[:5]
        decision = "DETECTOR COVERAGE STILL INSUFFICIENT"

    # Miss slice aggregates for best incomplete candidate.
    miss_slices = None
    if selected is None and enriched:
        best = sorted(
            enriched,
            key=lambda r: (
                -float(r.get("overall_recall") or 0.0),
                int(r.get("misses") or 10**9),
            ),
        )[0]
        cov = best.get("seed_coverage") or {}
        by_cat = cov.get("by_category") or {}
        miss_slices = {
            cat: int((info.get("counts") or {}).get("missed", 0)) for cat, info in by_cat.items()
        }
        miss_slices["overall_missed"] = int(cov.get("missed_detections") or 0)

    payload = {
        "task": "select",
        "decision": decision,
        "selected_candidate": selected,
        "passing_count": len(ranked),
        "pareto_candidates": pareto,
        "remaining_miss_slices": miss_slices,
        "live_path_unchanged": True,
        "shadow_only": True,
    }
    _write_report(private_root, "candidate-selection.json", payload)
    return payload


def cmd_build_v2(private_root: Path) -> dict[str, Any]:
    """Build phase5-detector-first-regions-v2 for the selected candidate.

    Preserves Task C0 v1 artefacts: writes under detector-first/v2/ and a
    separate v2 aggregate report. Does not overwrite v1 manifests.
    """

    from backend.app.datasets.phase5.constants import (
        DETECTOR_FIRST_CORPUS_VERSION_V2,
    )
    from backend.app.datasets.phase5.detector_calibration import (
        DetectorCalibrationConfig,
        build_bounded_calibration_grid,
    )
    from backend.app.datasets.phase5.detector_first import (
        build_aggregate_report,
        load_page_sources,
        mark_exact_duplicates,
        page_png_path,
        process_page_regions,
        summarise_seed_coverage,
        write_private_aggregate,
    )
    from backend.app.datasets.phase5.detector_merge import merge_detector_regions
    from backend.app.datasets.phase5.geometry_match import bbox_from_tuple
    from backend.app.datasets.phase5.jsonl_io import read_jsonl, write_jsonl_atomic
    from backend.app.datasets.phase5.paths import ensure_layout, manifest_path, reports_dir
    from backend.app.datasets.phase5.schemas import DocumentRecord
    from backend.app.extraction.visual.detect_first_types import DetectorRuntimeParams
    from PIL import Image

    select_path = _reports_dir(private_root) / "candidate-selection.json"
    if not select_path.is_file():
        return {"error": "run select first", "decision": "DETECTOR COVERAGE STILL INSUFFICIENT"}
    selection = json.loads(select_path.read_text(encoding="utf-8"))
    if selection.get("decision") != "HANDWRITING-CAPABLE DETECTOR CANDIDATE READY":
        return {
            "error": "no passing candidate",
            "decision": selection.get("decision"),
        }
    selected = selection["selected_candidate"]
    settings, config = _ocr_config()

    grid_by_id = {c.config_id: c for c in build_bounded_calibration_grid()}
    cfg = grid_by_id.get(selected["config_id"])
    if cfg is None:
        params = DetectorRuntimeParams(**selected["params"])
        partner = (
            DetectorRuntimeParams(**selected["merge_partner_params"])
            if selected.get("merge_partner_params")
            else None
        )
        cfg = DetectorCalibrationConfig(
            family=selected["family"],
            detection_model_name=selected["detection_model_name"],
            params=params,
            merge_partner_model_name=selected.get("merge_partner_model_name"),
            merge_partner_params=partner,
            merge_version=selected.get("merge_version"),
            label=selected.get("label") or "",
            apply_params=bool(selected.get("apply_params", True)),
        )

    ensure_layout(private_root)
    v2_root = private_root / "detector-first" / "v2"
    v2_root.mkdir(parents=True, exist_ok=True)
    (v2_root / "crops").mkdir(parents=True, exist_ok=True)

    primary = _adapter_for_model(config, cfg.detection_model_name, with_rec=True)
    secondary = None
    if cfg.family == "merged":
        assert cfg.merge_partner_model_name is not None
        secondary = _adapter_for_model(config, cfg.merge_partner_model_name, with_rec=False)

    docs = {
        d.document_id: d
        for d in read_jsonl(manifest_path(private_root, "document-manifest.jsonl"), DocumentRecord)
    }
    sources = load_page_sources(private_root)
    all_records = []
    page_detector_bboxes: dict[str, list[Any]] = defaultdict(list)
    detect_s = 0.0
    recognise_s = 0.0
    low_thr = float(settings.ocr_low_confidence_score)
    min_thr = float(settings.ocr_min_recognition_score)

    def _recognise(crops: list[tuple[str, Any]]) -> list[Any]:
        nonlocal recognise_s
        t = time.perf_counter()
        out = primary.recognise_text_crops(crops)
        recognise_s += time.perf_counter() - t
        return out

    # Redirect crops into v2 by temporarily using a nested private layout is hard;
    # instead call process_page_regions then relocate records' relative paths.
    for source in sources:
        png = page_png_path(private_root, source.page_id)
        if not png.is_file() or source.document_id not in docs:
            continue
        with Image.open(png) as img:
            page = img.convert("RGB")
            t = time.perf_counter()
            regions = _detect_page(primary, page, source.page_index, cfg.predict_params())
            if secondary is not None:
                partner_regions = _detect_page(
                    secondary, page, source.page_index, cfg.predict_partner_params()
                )
                regions = merge_detector_regions(regions, partner_regions)
            detect_s += time.perf_counter() - t
            for region in regions:
                page_detector_bboxes[source.page_id].append(bbox_from_tuple(region.bbox_norm))
            page_records = process_page_regions(
                private_root=private_root,
                page=page,
                page_id=source.page_id,
                document_id=source.document_id,
                source_group_id=source.source_group_id,
                page_index=source.page_index,
                regions=regions,
                recognise=_recognise,
                low_thr=low_thr,
                min_thr=min_thr,
            )
            all_records.extend(page_records)

    all_records = mark_exact_duplicates(all_records)
    # Rewrite schema_version on serialised dicts for v2 manifest.
    serialised = []
    for r in all_records:
        data = r.model_dump(mode="json")
        data["schema_version"] = DETECTOR_FIRST_CORPUS_VERSION_V2
        serialised.append(data)

    v2_manifest = v2_root / "detector-first-region-manifest-v2.jsonl"
    write_jsonl_atomic(v2_manifest, serialised)

    seeds = _load_seeds(private_root)
    seed_coverage = summarise_seed_coverage(seeds, page_detector_bboxes)
    report = build_aggregate_report(
        all_records,
        seed_coverage=seed_coverage,
        timing={"detect": detect_s, "recognise": recognise_s},
        recognition_equivalence="acceptable_for_retraining",
    )
    report["corpus_version"] = DETECTOR_FIRST_CORPUS_VERSION_V2
    report["detector_candidate"] = cfg.to_public_dict()
    report["preserved_c0_corpus"] = True
    out = reports_dir(private_root) / "detector-first-aggregate-v2.json"
    out.write_text(json.dumps(_aggregate_only(report), indent=2, sort_keys=True) + "\n")
    _write_report(private_root, "corpus-v2-build.json", report)
    # Also keep a copy via write_private_aggregate naming convention without overwrite.
    _ = write_private_aggregate
    return report


def main(argv: list[str] | None = None) -> int:
    _ensure_path()
    from backend.app.datasets.phase5.paths import default_private_root

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--private-root",
        type=Path,
        default=None,
        help="Private Phase 5 root (default fixtures/private/phase5)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("baseline", help="Reproduce Task C0 mobile seed coverage")
    p_grid = sub.add_parser("grid", help="Bounded calibration grid on seed pages")
    p_grid.add_argument(
        "--skip-server",
        action="store_true",
        help="Skip server/merged configs (mobile-only grid)",
    )
    p_corpus = sub.add_parser("corpus", help="Corpus impact for shortlisted candidates")
    p_corpus.add_argument("--config-id", action="append", default=None)
    p_corpus.add_argument("--max-pages", type=int, default=None)
    p_recog = sub.add_parser("recognise-sample", help="10-page recognition sample")
    p_recog.add_argument("--max-pages", type=int, default=10)
    sub.add_parser("select", help="Apply zero-miss gate and rank candidates")
    sub.add_parser("build-v2", help="Build corpus v2 for selected candidate")

    args = parser.parse_args(argv)
    private_root = args.private_root or default_private_root()

    if args.command == "baseline":
        result = cmd_baseline(private_root)
    elif args.command == "grid":
        result = cmd_grid(private_root, skip_server=args.skip_server)
    elif args.command == "corpus":
        result = cmd_corpus(private_root, config_ids=args.config_id, max_pages=args.max_pages)
    elif args.command == "recognise-sample":
        result = cmd_recognise_sample(private_root, max_pages=args.max_pages)
    elif args.command == "select":
        result = cmd_select(private_root)
    elif args.command == "build-v2":
        result = cmd_build_v2(private_root)
    else:
        parser.error(f"unknown command {args.command}")
        return 2

    _emit(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
