"""Long-lived visual OCR worker process.

Load PaddleOCR once, accept NDJSON document jobs on stdin, emit privacy-safe
progress on stdout, and write page results to the paths given in each request.
Never emit OCR text on stdout/stderr.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
import time
import traceback
import unicodedata
from pathlib import Path
from typing import Any

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.native import SourceMode
from backend.app.contracts.ocr import (
    HandwritingAssessment,
    OcrPassKind,
    OcrQualityStatus,
    OcrRecognitionStatus,
    PreprocessingVariant,
    PrintedOcrLine,
    PrintedOcrWord,
    ProvisionalItemClass,
    WordGeometrySource,
    WordScoreSource,
)
from backend.app.contracts.visual import VisualPageResult, VisualPageStatus, VisualWarning
from backend.app.contracts.warnings import NativeReasonCode, reason_message
from backend.app.extraction.visual.coordinates import map_pixel_polygon
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.grid import detect_grid_interference, is_suppressible_line_only
from backend.app.extraction.visual.layout import LayoutThresholds, group_lines_into_blocks
from backend.app.extraction.visual.models import (
    OcrRuntimeConfig,
    VisualPageRef,
    VisualWorkerRequest,
)
from backend.app.extraction.visual.noise import (
    classify_raw_lines,
    count_provisional_classes,
)
from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter
from backend.app.extraction.visual.page_profile import analyse_page_profile
from backend.app.extraction.visual.preprocessing import prepare_grayscale_fallback, prepare_primary
from backend.app.extraction.visual.protocol import emit_message, parse_message
from backend.app.extraction.visual.quality import (
    build_quality_evidence,
    compare_ocr_passes,
    count_valid_words,
)
from backend.app.extraction.visual.reading_order import (
    apply_block_reading_order_indices,
    build_reading_order,
)
from backend.app.extraction.visual.renderer import RenderLimits, open_document, render_page
from backend.app.extraction.visual.resource_monitor import ResourceMonitor
from backend.app.extraction.visual.result_store import write_page_atomic

logger = logging.getLogger("veridemand.visual.worker")

_STDERR_MAX_BYTES = 8_192
_active_cancel_request_id: str | None = None


def _bounded_stderr(message: str) -> None:
    data = message.encode("utf-8", errors="replace")[:_STDERR_MAX_BYTES]
    sys.stderr.buffer.write(data)
    if not data.endswith(b"\n"):
        sys.stderr.buffer.write(b"\n")
    sys.stderr.flush()


def _config_from_env_settings() -> OcrRuntimeConfig:
    from backend.app.extraction.visual.model_paths import resolve_ocr_model_root
    from backend.app.settings.config import Settings

    settings = Settings()
    return OcrRuntimeConfig(
        ocr_enabled=settings.ocr_enabled,
        ocr_device=settings.ocr_device,
        ocr_engine=settings.ocr_engine,
        ocr_detection_model_name=settings.ocr_detection_model_name,
        ocr_recognition_model_name=settings.ocr_recognition_model_name,
        ocr_model_root=str(resolve_ocr_model_root(settings.ocr_model_root)),
        ocr_cpu_threads=settings.ocr_cpu_threads,
        ocr_recognition_batch_size=settings.ocr_recognition_batch_size,
        ocr_render_dpi=settings.ocr_render_dpi,
        ocr_visibility_probe_dpi=settings.ocr_visibility_probe_dpi,
        ocr_min_effective_dpi=settings.ocr_min_effective_dpi,
        ocr_max_render_pixels=settings.ocr_max_render_pixels,
        ocr_max_render_side_pixels=settings.ocr_max_render_side_pixels,
        ocr_text_det_limit_side_len=settings.ocr_text_det_limit_side_len,
        ocr_text_det_limit_type=settings.ocr_text_det_limit_type,
        ocr_text_det_thresh=settings.ocr_text_det_thresh,
        ocr_text_det_box_thresh=settings.ocr_text_det_box_thresh,
        ocr_text_det_unclip_ratio=settings.ocr_text_det_unclip_ratio,
        ocr_min_recognition_score=settings.ocr_min_recognition_score,
        ocr_low_confidence_score=settings.ocr_low_confidence_score,
        ocr_enable_grayscale_fallback=settings.ocr_enable_grayscale_fallback,
        ocr_fallback_max_attempts=settings.ocr_fallback_max_attempts,
        ocr_page_timeout_seconds=settings.ocr_page_timeout_seconds,
        ocr_max_worker_rss_mb=settings.ocr_max_worker_rss_mb,
        ocr_worker_recycle_after_pages=settings.ocr_worker_recycle_after_pages,
        ocr_save_rendered_pages=settings.ocr_save_rendered_pages,
        ocr_keep_failed_render=settings.ocr_keep_failed_render,
        ocr_layout_max_vertical_gap_ratio=settings.ocr_layout_max_vertical_gap_ratio,
        ocr_layout_min_horizontal_overlap_ratio=settings.ocr_layout_min_horizontal_overlap_ratio,
        ocr_column_gap_ratio=settings.ocr_column_gap_ratio,
        canonical_page_dimension_tolerance_points=(
            settings.canonical_page_dimension_tolerance_points
        ),
        ocr_fast_pass_enabled=settings.ocr_fast_pass_enabled,
        ocr_primary_limit_side_len=settings.ocr_primary_limit_side_len,
        ocr_fallback_limit_side_len=settings.ocr_fallback_limit_side_len,
        ocr_fast_pass_min_detections=settings.ocr_fast_pass_min_detections,
        ocr_fast_pass_min_average_confidence=settings.ocr_fast_pass_min_average_confidence,
        ocr_fast_pass_min_coverage=settings.ocr_fast_pass_min_coverage,
    )


def _recognition_status(score: float, *, low: float, minimum: float) -> OcrRecognitionStatus:
    if score < minimum or score < low:
        return OcrRecognitionStatus.LOW_CONFIDENCE
    return OcrRecognitionStatus.ACCEPTED


def _raw_needs_fallback(raw_lines: list[Any], config: OcrRuntimeConfig) -> bool:
    if not raw_lines:
        return True
    avg = sum(float(r.recognition_score) for r in raw_lines) / len(raw_lines)
    return avg < config.ocr_min_recognition_score


def _build_contract_lines(
    raw_lines: list[Any],
    *,
    page_number: int,
    width_pixels: int,
    height_pixels: int,
    variant: PreprocessingVariant,
    config: OcrRuntimeConfig,
    ocr_pass: OcrPassKind | None = None,
    provisional_by_index: dict[int, ProvisionalItemClass] | None = None,
    publish_indices: set[int] | None = None,
) -> tuple[list[PrintedOcrLine], list[PrintedOcrWord]]:
    lines: list[PrintedOcrLine] = []
    words: list[PrintedOcrWord] = []
    word_seq = 0
    for line_index, raw in enumerate(raw_lines):
        if publish_indices is not None and line_index not in publish_indices:
            continue
        try:
            mapped = map_pixel_polygon(
                raw.polygon_px, width_pixels=width_pixels, height_pixels=height_pixels
            )
        except VisualOcrError:
            continue
        line_id = f"ocrline_p{page_number:04d}_{line_index + 1:06d}"
        status = _recognition_status(
            float(raw.recognition_score),
            low=config.ocr_low_confidence_score,
            minimum=config.ocr_min_recognition_score,
        )
        normalised = unicodedata.normalize("NFC", str(raw.text))
        provisional = (provisional_by_index or {}).get(line_index)
        lines.append(
            PrintedOcrLine(
                id=line_id,
                page_number=page_number,
                sequence_index=line_index,
                text=str(raw.text),
                normalised_text=normalised,
                detection_score=float(raw.detection_score),
                recognition_score=float(raw.recognition_score),
                recognition_status=status,
                polygon=mapped.polygon,
                bbox=mapped.bbox,
                geometry=mapped.geometry,
                pixel_polygon=mapped.pixel_polygon,
                pixel_bbox=mapped.pixel_bbox,
                preprocessing_variant=variant,
                ocr_pass=ocr_pass,
                provisional_class=provisional,
                handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
            )
        )
        for raw_word in raw.words:
            try:
                word_mapped = map_pixel_polygon(
                    raw_word.polygon_px, width_pixels=width_pixels, height_pixels=height_pixels
                )
            except VisualOcrError:
                continue
            word_seq += 1
            geom_source = (
                WordGeometrySource.PADDLE_WORD_BOX
                if raw_word.geometry_source == "paddle_word_box"
                else WordGeometrySource.DERIVED_FROM_LINE_POLYGON
            )
            score_source = (
                WordScoreSource.PADDLE_RECOGNITION
                if raw_word.score_source == "paddle_recognition"
                else WordScoreSource.INHERITED_FROM_LINE
            )
            words.append(
                PrintedOcrWord(
                    id=f"ocrword_p{page_number:04d}_{word_seq:06d}",
                    page_number=page_number,
                    line_id=line_id,
                    sequence_index=word_seq - 1,
                    text=str(raw_word.text),
                    normalised_text=unicodedata.normalize("NFC", str(raw_word.text)),
                    recognition_score=float(raw_word.score),
                    score_source=score_source,
                    polygon=word_mapped.polygon,
                    bbox=word_mapped.bbox,
                    geometry=word_mapped.geometry,
                    pixel_polygon=word_mapped.pixel_polygon,
                    pixel_bbox=word_mapped.pixel_bbox,
                    geometry_source=geom_source,
                    geometry_precision=(
                        "detector"
                        if geom_source is WordGeometrySource.PADDLE_WORD_BOX
                        else "approximate"
                    ),
                    recognition_status=_recognition_status(
                        float(raw_word.score),
                        low=config.ocr_low_confidence_score,
                        minimum=config.ocr_min_recognition_score,
                    ),
                    ocr_pass=ocr_pass,
                    provisional_class=provisional,
                )
            )
    return lines, words


def _aggregate_scores(lines: list[PrintedOcrLine]) -> tuple[float | None, float | None, int]:
    if not lines:
        return None, None, 0
    det = sum(line.detection_score for line in lines) / len(lines)
    rec = sum(line.recognition_score for line in lines) / len(lines)
    low = sum(1 for line in lines if line.recognition_status is OcrRecognitionStatus.LOW_CONFIDENCE)
    return det, rec, low


def process_page(
    *,
    pdf_path: Path,
    page_ref: VisualPageRef,
    config: OcrRuntimeConfig,
    adapter: PaddleOcrAdapter,
    pdf_document: Any,
    monitor: ResourceMonitor,
    request_id: str,
) -> VisualPageResult:
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    started = time.perf_counter()
    page_timeout = float(config.ocr_page_timeout_seconds)
    limits = RenderLimits(
        target_dpi=float(config.ocr_render_dpi),
        min_effective_dpi=float(config.ocr_min_effective_dpi),
        max_render_pixels=config.ocr_max_render_pixels,
        max_render_side_pixels=config.ocr_max_render_side_pixels,
        dimension_tolerance_points=config.canonical_page_dimension_tolerance_points,
    )
    emit_message(
        {
            "type": "page.started",
            "request_id": request_id,
            "page_number": page_ref.page_number,
        }
    )

    def _render() -> Any:
        return render_page(
            pdf_path,
            page_number=page_ref.page_number,
            page_width_points=page_ref.width_points,
            page_height_points=page_ref.height_points,
            limits=limits,
            pdf_document=pdf_document,
        )

    preprocess_started = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            rendered = pool.submit(_render).result(timeout=page_timeout)
    except FuturesTimeout as exc:
        raise VisualOcrError(
            ErrorCode.OCR_PAGE_TIMEOUT,
            "Page render timed out.",
            operation="render_page",
            failing_component="visual.worker",
            exception_type=type(exc).__name__,
        ) from exc
    render_duration_s = time.perf_counter() - preprocess_started
    rendered.detector_limit_side_len = int(config.ocr_text_det_limit_side_len)
    # Detector input after Paddle limit_side resize (max side).
    det_w, det_h = rendered.width_pixels, rendered.height_pixels
    limit = max(1, int(config.ocr_text_det_limit_side_len))
    if config.ocr_text_det_limit_type == "max":
        long_side = max(det_w, det_h)
        if long_side > limit:
            scale = limit / long_side
            det_w = max(1, int(det_w * scale))
            det_h = max(1, int(det_h * scale))
    emit_message(
        {
            "type": "page.rendered",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "width_pixels": rendered.width_pixels,
            "height_pixels": rendered.height_pixels,
            "rendered_pixel_count": rendered.width_pixels * rendered.height_pixels,
            "effective_dpi": rendered.effective_dpi,
            "requested_dpi": rendered.requested_dpi,
            "canonical_width_points": rendered.page_width_points,
            "canonical_height_points": rendered.page_height_points,
            "source_width_px": rendered.source_width_px,
            "source_height_px": rendered.source_height_px,
            "render_source_policy": rendered.render_source_policy,
            "downscale_reason": rendered.downscale_reason,
            "source_resolution_cap_applied": rendered.source_resolution_cap_applied,
            "detector_limit_side_len": rendered.detector_limit_side_len,
            "detector_input_width": det_w,
            "detector_input_height": det_h,
            "render_duration_seconds": round(render_duration_s, 3),
            "peak_rss_mb": monitor.snapshot().rss_mb,
        }
    )

    prep_started = time.perf_counter()
    primary_image, variant = prepare_primary(rendered.image)
    preprocess_duration_s = time.perf_counter() - prep_started
    emit_message(
        {
            "type": "page.ocr_started",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "preprocess_duration_seconds": round(preprocess_duration_s, 3),
            "detector_input_width": det_w,
            "detector_input_height": det_h,
            "detector_limit_side_len": limit,
            "operation": "paddle_ocr_pipeline",
        }
    )
    pipeline_started = time.perf_counter()
    primary_limit = int(
        getattr(config, "ocr_primary_limit_side_len", config.ocr_text_det_limit_side_len)
    )
    fallback_limit = int(
        getattr(config, "ocr_fallback_limit_side_len", config.ocr_text_det_limit_side_len)
    )
    fast_pass = bool(getattr(config, "ocr_fast_pass_enabled", False))
    active_limit = primary_limit if fast_pass else int(config.ocr_text_det_limit_side_len)
    emit_message(
        {
            "type": "full_ocr_primary_started",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "primary_limit_side": active_limit,
            "operation": "full_ocr_primary",
        }
    )

    def _recognise(image: Any, limit_side: int) -> list[Any]:
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(adapter.recognise, image, limit_side_len=limit_side).result(
                    timeout=page_timeout
                )
        except TypeError:
            with ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(adapter.recognise, image).result(timeout=page_timeout)

    try:
        primary_raw = _recognise(primary_image, active_limit)
    except FuturesTimeout as exc:
        raise VisualOcrError(
            ErrorCode.OCR_PAGE_TIMEOUT,
            "OCR inference timed out.",
            operation="paddle_ocr_pipeline",
            failing_component="visual.worker",
            exception_type=type(exc).__name__,
        ) from exc
    primary_duration_ms = int((time.perf_counter() - pipeline_started) * 1000)
    primary_conf = None
    if primary_raw:
        primary_conf = sum(line.recognition_score for line in primary_raw) / len(primary_raw)
    emit_message(
        {
            "type": "full_ocr_primary_completed",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "primary_limit_side": active_limit,
            "primary_duration_ms": primary_duration_ms,
            "primary_detection_count": len(primary_raw),
            "primary_average_confidence": primary_conf,
            "operation": "full_ocr_primary",
        }
    )

    profile = analyse_page_profile(primary_image, raw_lines=primary_raw)
    grid = detect_grid_interference(primary_image, primary_raw)
    emit_message(
        {
            "type": "full_ocr_quality_evaluation_started",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "full_ocr_quality_evaluation",
            "page_profile": profile.page_profile.value,
        }
    )
    primary_quality = build_quality_evidence(
        primary_raw,
        page_number=page_ref.page_number,
        ocr_pass=OcrPassKind.PRIMARY,
        detector_limit_side=active_limit,
        page_width=primary_image.size[0],
        page_height=primary_image.size[1],
        low_confidence_threshold=config.ocr_low_confidence_score,
        preprocessing_variant=variant,
        profile=profile,
        grid=grid,
        route="full_visual_ocr",
    )
    emit_message(
        {
            "type": "full_ocr_quality_evaluation_completed",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "full_ocr_quality_evaluation",
            "page_profile": primary_quality.page_profile.value,
            "quality_policy_version": primary_quality.policy_version,
            "primary_limit_side": active_limit,
            "primary_quality_status": primary_quality.quality_status.value,
            "primary_fragmentation_score": primary_quality.fragmentation_score,
            "primary_low_confidence_ratio": primary_quality.low_confidence_ratio,
            "primary_symbol_ratio": primary_quality.symbol_only_token_ratio,
            "fallback_recommended": primary_quality.fallback_recommended,
            "fallback_reason_codes": list(primary_quality.fallback_reason_codes),
            "quality_gate_passed": primary_quality.quality_gate_passed,
        }
    )

    fallback_raw: list[Any] | None = None
    fallback_quality = None
    fallback_side_used = False
    fallback_duration_ms: int | None = None
    fallback_limit_used: int | None = None
    rss_before_fallback = monitor.snapshot().rss_mb

    if (
        fast_pass
        and active_limit < fallback_limit
        and primary_quality.fallback_recommended
        and not primary_quality.quality_gate_passed
    ):
        fallback_limit_used = fallback_limit
        emit_message(
            {
                "type": "full_ocr_fallback_started",
                "request_id": request_id,
                "page_number": page_ref.page_number,
                "fallback_limit_side": fallback_limit,
                "fallback_reason_codes": list(primary_quality.fallback_reason_codes),
                "operation": "full_ocr_fallback",
            }
        )
        fallback_started = time.perf_counter()
        try:
            fallback_raw = _recognise(primary_image, fallback_limit)
        except FuturesTimeout as exc:
            raise VisualOcrError(
                ErrorCode.OCR_PAGE_TIMEOUT,
                "OCR fallback inference timed out.",
                operation="paddle_ocr_pipeline",
                failing_component="visual.worker",
                exception_type=type(exc).__name__,
            ) from exc
        fallback_side_used = True
        fallback_duration_ms = int((time.perf_counter() - fallback_started) * 1000)
        fallback_grid = detect_grid_interference(primary_image, fallback_raw)
        fallback_profile = analyse_page_profile(primary_image, raw_lines=fallback_raw)
        fallback_quality = build_quality_evidence(
            fallback_raw,
            page_number=page_ref.page_number,
            ocr_pass=OcrPassKind.FALLBACK,
            detector_limit_side=fallback_limit,
            page_width=primary_image.size[0],
            page_height=primary_image.size[1],
            low_confidence_threshold=config.ocr_low_confidence_score,
            preprocessing_variant=variant,
            profile=fallback_profile,
            grid=fallback_grid,
            route="full_visual_ocr",
        )
        emit_message(
            {
                "type": "full_ocr_fallback_completed",
                "request_id": request_id,
                "page_number": page_ref.page_number,
                "fallback_limit_side": fallback_limit,
                "fallback_duration_ms": fallback_duration_ms,
                "fallback_quality_status": fallback_quality.quality_status.value,
                "fallback_memory_delta_mb": round(
                    monitor.snapshot().rss_mb - rss_before_fallback, 2
                ),
                "operation": "full_ocr_fallback",
            }
        )

    emit_message(
        {
            "type": "full_ocr_result_selection_started",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "full_ocr_result_selection",
        }
    )
    comparison = compare_ocr_passes(
        primary_quality,
        fallback_quality,
        primary_valid_words=count_valid_words(
            primary_raw, min_score=config.ocr_min_recognition_score
        ),
        fallback_valid_words=count_valid_words(
            fallback_raw or [], min_score=config.ocr_min_recognition_score
        ),
    )
    selected_pass = comparison.selected_pass
    if selected_pass is OcrPassKind.FALLBACK and fallback_raw is not None:
        raw_lines = fallback_raw
        selected_quality = fallback_quality or primary_quality
    else:
        raw_lines = primary_raw
        selected_pass = OcrPassKind.PRIMARY
        selected_quality = primary_quality
        if fallback_raw is not None:
            del fallback_raw
            fallback_raw = None
    emit_message(
        {
            "type": "full_ocr_result_selection_completed",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "full_ocr_result_selection",
            "selected_pass": selected_pass.value,
            "selection_reason_codes": list(comparison.selection_reason_codes),
            "primary_limit_side": active_limit,
            "fallback_limit_side": fallback_limit_used,
            "fallback_triggered": fallback_side_used,
        }
    )

    paddle_pipeline_duration_s = time.perf_counter() - pipeline_started
    emit_message(
        {
            "type": "page.ocr_completed",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "paddle_ocr_pipeline",
            "paddle_pipeline_duration_seconds": round(paddle_pipeline_duration_s, 3),
            "detected_line_count": len(raw_lines),
            "fast_pass_fallback_used": fallback_side_used,
            "selected_ocr_pass": selected_pass.value,
            "peak_rss_mb": monitor.snapshot().rss_mb,
        }
    )
    grayscale_fallback_used = False
    if (
        config.ocr_enable_grayscale_fallback
        and config.ocr_fallback_max_attempts >= 1
        and _raw_needs_fallback(raw_lines, config)
        and not fallback_side_used
    ):
        fallback_image, variant = prepare_grayscale_fallback(rendered.image)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                raw_lines = pool.submit(adapter.recognise, fallback_image).result(
                    timeout=page_timeout
                )
        except FuturesTimeout as exc:
            fallback_image.close()
            raise VisualOcrError(
                ErrorCode.OCR_PAGE_TIMEOUT,
                "OCR fallback inference timed out.",
                operation="paddle_ocr_pipeline",
                failing_component="visual.worker",
                exception_type=type(exc).__name__,
            ) from exc
        grayscale_fallback_used = True
        fallback_image.close()

    # Suppress confidently line-only detections before contract mapping.
    selected_grid = detect_grid_interference(primary_image, raw_lines)
    line_only = set(selected_grid.line_only_detection_indices)
    suppressible = {
        idx for idx in line_only if is_suppressible_line_only(raw_lines[idx], line_only_index=True)
    }
    dense = profile.page_profile.value == "dense_form"
    classified = classify_raw_lines(
        raw_lines,
        low_confidence_threshold=config.ocr_low_confidence_score,
        line_only_indices=line_only,
        page_has_dense_form=dense,
    )
    provisional_by_index = {c.index: c.provisional_class for c in classified}
    # Transcript publish set: credible + low-confidence; keep geometry for others via
    # diagnostics counts only (artefacts not mixed into provisional reading text).
    publish_indices = {
        c.index for c in classified if c.publish_in_transcript and c.index not in suppressible
    }
    # Always retain unresolved/handwriting geometry in overlay diagnostics by publishing
    # low-confidence and credible only in lines list; artefact indices excluded.
    provisional_counts = count_provisional_classes(classified)

    primary_image.close()
    rendered.image.close()

    emit_message(
        {
            "type": "page.mapping_started",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "visual_coordinate_mapping",
        }
    )
    map_started = time.perf_counter()
    lines, words = _build_contract_lines(
        raw_lines,
        page_number=page_ref.page_number,
        width_pixels=rendered.width_pixels,
        height_pixels=rendered.height_pixels,
        variant=variant,
        config=config,
        ocr_pass=selected_pass,
        provisional_by_index=provisional_by_index,
        publish_indices=publish_indices,
    )
    mapping_duration_s = time.perf_counter() - map_started
    emit_message(
        {
            "type": "page.mapping_completed",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "visual_coordinate_mapping",
            "mapping_duration_seconds": round(mapping_duration_s, 3),
            "line_count": len(lines),
            "word_count": len(words),
        }
    )

    emit_message(
        {
            "type": "page.grouping_started",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "visual_line_grouping",
        }
    )
    group_started = time.perf_counter()
    blocks = group_lines_into_blocks(
        lines,
        page_number=page_ref.page_number,
        thresholds=LayoutThresholds(
            max_vertical_gap_ratio=config.ocr_layout_max_vertical_gap_ratio,
            min_horizontal_overlap_ratio=config.ocr_layout_min_horizontal_overlap_ratio,
            column_gap_ratio=config.ocr_column_gap_ratio,
        ),
    )
    blocks = apply_block_reading_order_indices(blocks)
    reading_order = build_reading_order(lines, blocks)
    grouping_duration_s = time.perf_counter() - group_started
    emit_message(
        {
            "type": "page.grouping_completed",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "operation": "visual_line_grouping",
            "grouping_duration_seconds": round(grouping_duration_s, 3),
            "block_count": len(blocks),
        }
    )
    avg_det, avg_rec, low_count = _aggregate_scores(lines)

    warnings: list[VisualWarning] = []
    if not lines:
        status = VisualPageStatus.COMPLETED_NO_TEXT
        warnings.append(
            VisualWarning(
                code=NativeReasonCode.OCR_NO_TEXT_DETECTED.value,
                message=reason_message(NativeReasonCode.OCR_NO_TEXT_DETECTED.value),
                page_number=page_ref.page_number,
            )
        )
    else:
        status = VisualPageStatus.COMPLETED
        if low_count:
            warnings.append(
                VisualWarning(
                    code=NativeReasonCode.OCR_LOW_CONFIDENCE.value,
                    message=reason_message(NativeReasonCode.OCR_LOW_CONFIDENCE.value),
                    page_number=page_ref.page_number,
                )
            )
        if selected_quality.quality_status in {
            OcrQualityStatus.LOW_QUALITY,
            OcrQualityStatus.INSUFFICIENT,
        } or (
            fallback_side_used
            and comparison.selected_pass is OcrPassKind.PRIMARY
            and "fallback_no_measured_improvement" in comparison.selection_reason_codes
        ):
            warnings.append(
                VisualWarning(
                    code=NativeReasonCode.OCR_LOW_CONFIDENCE.value,
                    message="Printed OCR quality is low; fallback did not improve the result.",
                    page_number=page_ref.page_number,
                )
            )

    duration_ms = int((time.perf_counter() - started) * 1000)
    snap = monitor.snapshot()
    monitor.note_page_completed()
    source_mode = (
        SourceMode.IMAGE_AUTHORITY
        if page_ref.source_type == "image"
        else SourceMode.VISUAL_AUTHORITY
    )
    return VisualPageResult(
        page_number=page_ref.page_number,
        status=status,
        source_mode=source_mode,
        render_dpi=rendered.effective_dpi,
        render_width_pixels=rendered.width_pixels,
        render_height_pixels=rendered.height_pixels,
        preprocessing_variant=variant,
        fallback_used=fallback_side_used or grayscale_fallback_used,
        selected_ocr_pass=selected_pass,
        primary_quality_status=primary_quality.quality_status,
        fallback_quality_status=(
            fallback_quality.quality_status if fallback_quality is not None else None
        ),
        fallback_reason_codes=list(primary_quality.fallback_reason_codes),
        quality_policy_version=primary_quality.policy_version,
        page_profile=primary_quality.page_profile,
        page_profile_reason_codes=list(primary_quality.profile_reason_codes),
        primary_quality=primary_quality,
        fallback_quality=fallback_quality,
        ocr_pass_comparison=comparison,
        provisional_item_counts=provisional_counts,
        primary_limit_side=active_limit,
        fallback_limit_side=fallback_limit_used,
        fallback_duration_ms=fallback_duration_ms,
        line_count=len(lines),
        word_count=len(words),
        average_detection_score=avg_det,
        average_recognition_score=avg_rec,
        low_confidence_line_count=low_count,
        lines=lines,
        words=words,
        blocks=blocks,
        reading_order=reading_order,
        visual_result_available=bool(lines),
        visual_processing_attempted=True,
        handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
        warnings=warnings,
        duration_ms=duration_ms,
        peak_rss_mb=snap.rss_mb,
        render_duration_seconds=round(render_duration_s, 3),
        preprocess_duration_seconds=round(preprocess_duration_s, 3),
        paddle_pipeline_duration_seconds=round(paddle_pipeline_duration_s, 3),
        mapping_duration_seconds=round(mapping_duration_s, 3),
        grouping_duration_seconds=round(grouping_duration_s, 3),
        source_width_px=rendered.source_width_px,
        source_height_px=rendered.source_height_px,
        detector_input_width=det_w,
        detector_input_height=det_h,
        requested_dpi=rendered.requested_dpi,
        render_source_policy=rendered.render_source_policy,
        detection_model_name=config.ocr_detection_model_name,
        recognition_model_name=config.ocr_recognition_model_name,
        cpu_threads=config.ocr_cpu_threads,
        error_code=NativeReasonCode.OCR_NO_TEXT_DETECTED.value if not lines else None,
    )


def _failed_page(page_number: int, code: ErrorCode, source_type: str) -> VisualPageResult:
    return VisualPageResult(
        page_number=page_number,
        status=VisualPageStatus.FAILED,
        source_mode=(
            SourceMode.IMAGE_AUTHORITY if source_type == "image" else SourceMode.VISUAL_AUTHORITY
        ),
        visual_result_available=False,
        visual_processing_attempted=True,
        warnings=[
            VisualWarning(
                code=code.value,
                message="Visual OCR failed for this page.",
                page_number=page_number,
            )
        ],
        error_code=code.value,
    )


def process_document(request: VisualWorkerRequest, adapter: PaddleOcrAdapter) -> None:
    global _active_cancel_request_id

    emit_message(
        {
            "type": "document.started",
            "request_id": request.request_id,
            "page_count": len(request.pages),
        }
    )
    output_dir = Path(request.page_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = Path(request.canonical_pdf_path)
    monitor = ResourceMonitor(
        max_rss_mb=float(request.config.ocr_max_worker_rss_mb),
        recycle_after_pages=request.config.ocr_worker_recycle_after_pages,
    )
    skip = set(request.skip_page_numbers)
    doc = open_document(pdf_path)
    try:
        for page_ref in request.pages:
            if _active_cancel_request_id == request.request_id:
                emit_message(
                    {
                        "type": "document.cancelled",
                        "request_id": request.request_id,
                        "page_number": page_ref.page_number,
                    }
                )
                return
            if page_ref.page_number in skip:
                continue
            try:
                page_result = process_page(
                    pdf_path=pdf_path,
                    page_ref=page_ref,
                    config=request.config,
                    adapter=adapter,
                    pdf_document=doc,
                    monitor=monitor,
                    request_id=request.request_id,
                )
            except VisualOcrError as exc:
                page_result = _failed_page(page_ref.page_number, exc.code, page_ref.source_type)
                emit_message(
                    {
                        "type": "page.failed",
                        "request_id": request.request_id,
                        "page_number": page_ref.page_number,
                        "code": exc.code.value,
                        "operation": exc.operation,
                    }
                )
            except Exception as exc:
                _bounded_stderr(f"{type(exc).__name__}: page={page_ref.page_number}")
                page_result = _failed_page(
                    page_ref.page_number, ErrorCode.OCR_RECOGNITION_FAILED, page_ref.source_type
                )
                emit_message(
                    {
                        "type": "page.failed",
                        "request_id": request.request_id,
                        "page_number": page_ref.page_number,
                        "code": ErrorCode.OCR_RECOGNITION_FAILED.value,
                        "exception_type": type(exc).__name__,
                    }
                )

            write_page_atomic(output_dir, page_result)
            emit_message(
                {
                    "type": "page.completed",
                    "request_id": request.request_id,
                    "page_number": page_result.page_number,
                    "line_count": page_result.line_count,
                    "word_count": page_result.word_count,
                    "duration_ms": page_result.duration_ms,
                    "status": page_result.status.value,
                }
            )
            snap = monitor.snapshot()
            if snap.recycle_recommended:
                emit_message(
                    {
                        "type": "worker.recycle_recommended",
                        "rss_mb": snap.rss_mb,
                        "pages_since_start": snap.pages_since_start,
                    }
                )
    finally:
        with contextlib.suppress(Exception):
            doc.close()
        _active_cancel_request_id = None

    emit_message({"type": "document.completed", "request_id": request.request_id})


def run_worker_loop() -> int:
    logging.basicConfig(level=logging.INFO)
    emit_message({"type": "worker.starting"})

    import os

    from backend.app.contracts.ocr_runtime import OcrRuntimeErrorCode, OcrRuntimeStage
    from backend.app.extraction.visual.ocr_readiness import (
        classify_exception,
        operator_hint_for,
        sanitize_technical_detail,
        user_message_for,
    )
    from backend.app.settings.config import Settings

    settings = Settings()
    delay = float(settings.ocr_test_startup_delay_seconds or 0.0)
    if delay > 0:
        time.sleep(delay)

    fail_code = (settings.ocr_test_fail_once_code or settings.ocr_test_fail_code or "").strip()
    fail_once = bool(settings.ocr_test_fail_once_code)
    if fail_code:
        try:
            injected = OcrRuntimeErrorCode(fail_code)
        except ValueError:
            injected = OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE
        if fail_once:
            # Consume one-shot injection for this worker process only.
            os.environ.pop("OCR_TEST_FAIL_ONCE_CODE", None)
        emit_message(
            {
                "type": "worker.failed",
                "error_code": injected.value,
                "operation": "test_inject",
                "component": "ocr_worker",
                "exception_type": "TestInjectedFailure",
                "user_message": user_message_for(injected),
                "operator_hint": operator_hint_for(injected),
                "technical_detail": sanitize_technical_detail(f"test_inject:{injected.value}"),
            }
        )
        return 1

    def _on_stage(stage: OcrRuntimeStage) -> None:
        emit_message({"type": "worker.stage", "stage": stage.value})

    try:
        config = _config_from_env_settings()
        adapter = PaddleOcrAdapter(config)
        adapter.load(on_stage=_on_stage)
    except VisualOcrError as exc:
        readiness_code, detail = classify_exception(
            Exception(exc.exception_type or exc.message),
            operation=exc.operation,
            legacy_code=exc.code,
        )
        # Prefer embedded readiness code from exception_type when present.
        if exc.exception_type and ":" in exc.exception_type:
            maybe = exc.exception_type.split(":", 1)[1]
            with contextlib.suppress(ValueError):
                readiness_code = OcrRuntimeErrorCode(maybe)
        emit_message(
            {
                "type": "worker.failed",
                "error_code": readiness_code.value,
                "code": exc.code.value,
                "operation": exc.operation,
                "component": exc.failing_component,
                "exception_type": exc.exception_type,
                "user_message": user_message_for(readiness_code),
                "operator_hint": operator_hint_for(readiness_code),
                "technical_detail": detail,
            }
        )
        return 1
    except Exception as exc:
        _bounded_stderr(traceback.format_exc()[-_STDERR_MAX_BYTES:])
        readiness_code, detail = classify_exception(exc, operation="paddleocr_init")
        emit_message(
            {
                "type": "worker.failed",
                "error_code": readiness_code.value,
                "code": ErrorCode.OCR_MODEL_LOAD_FAILED.value,
                "exception_type": type(exc).__name__,
                "user_message": user_message_for(readiness_code),
                "operator_hint": operator_hint_for(readiness_code),
                "technical_detail": detail,
            }
        )
        return 1

    emit_message(
        {
            "type": "worker.ready",
            "paddleocr_version": adapter.paddleocr_version,
            "paddlepaddle_version": adapter.paddlepaddle_version,
            "word_box_key": adapter.schema.word_box_key if adapter.schema else None,
            "enable_mkldnn": False,
            "cpu_threads": config.ocr_cpu_threads,
            "ocr_device": config.ocr_device,
            "ocr_engine": config.ocr_engine,
        }
    )

    global _active_cancel_request_id
    for raw_line in sys.stdin:
        message = parse_message(raw_line)
        if message is None:
            continue
        msg_type = str(message.get("type") or "")
        if msg_type == "shutdown":
            emit_message({"type": "worker.shutdown"})
            return 0
        if msg_type == "ping":
            emit_message({"type": "pong"})
            continue
        if msg_type == "cancel":
            _active_cancel_request_id = str(message.get("request_id") or "")
            emit_message({"type": "cancel.accepted", "request_id": _active_cancel_request_id})
            continue
        if msg_type == "process_document":
            try:
                request = VisualWorkerRequest.from_dict(message["request"])
            except Exception as exc:
                emit_message(
                    {
                        "type": "error",
                        "code": ErrorCode.OCR_RESULT_INVALID.value,
                        "exception_type": type(exc).__name__,
                        "operation": "parse_request",
                    }
                )
                continue
            try:
                process_document(request, adapter)
            except Exception as exc:
                _bounded_stderr(f"{type(exc).__name__}")
                emit_message(
                    {
                        "type": "error",
                        "code": ErrorCode.OCR_WORKER_CRASHED.value,
                        "request_id": request.request_id,
                        "exception_type": type(exc).__name__,
                    }
                )
            continue
        emit_message({"type": "error", "code": "unknown_message", "message_type": msg_type})

    emit_message({"type": "worker.shutdown"})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="VeriDemand long-lived visual OCR worker")
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Load models, emit worker.ready, and exit.",
    )
    args = parser.parse_args(argv)
    if args.self_check:
        logging.basicConfig(level=logging.INFO)
        try:
            config = _config_from_env_settings()
            adapter = PaddleOcrAdapter(config)
            adapter.load()
            emit_message(
                {
                    "type": "worker.ready",
                    "self_check": True,
                    "paddleocr_version": adapter.paddleocr_version,
                }
            )
            return 0
        except Exception as exc:
            emit_message(
                {
                    "type": "error",
                    "code": ErrorCode.OCR_MODEL_LOAD_FAILED.value,
                    "exception_type": type(exc).__name__,
                }
            )
            return 1
    return run_worker_loop()


if __name__ == "__main__":
    raise SystemExit(main())
