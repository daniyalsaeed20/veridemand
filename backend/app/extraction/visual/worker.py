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
    OcrRecognitionStatus,
    PreprocessingVariant,
    PrintedOcrLine,
    PrintedOcrWord,
    WordGeometrySource,
    WordScoreSource,
)
from backend.app.contracts.visual import VisualPageResult, VisualPageStatus, VisualWarning
from backend.app.contracts.warnings import NativeReasonCode, reason_message
from backend.app.extraction.visual.coordinates import map_pixel_polygon
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.layout import LayoutThresholds, group_lines_into_blocks
from backend.app.extraction.visual.models import (
    OcrRuntimeConfig,
    VisualPageRef,
    VisualWorkerRequest,
)
from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter
from backend.app.extraction.visual.preprocessing import prepare_grayscale_fallback, prepare_primary
from backend.app.extraction.visual.protocol import emit_message, parse_message
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
    from backend.app.settings.config import Settings

    settings = Settings()
    return OcrRuntimeConfig(
        ocr_enabled=settings.ocr_enabled,
        ocr_device=settings.ocr_device,
        ocr_engine=settings.ocr_engine,
        ocr_detection_model_name=settings.ocr_detection_model_name,
        ocr_recognition_model_name=settings.ocr_recognition_model_name,
        ocr_model_root=str(settings.ocr_model_root),
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
) -> tuple[list[PrintedOcrLine], list[PrintedOcrWord]]:
    lines: list[PrintedOcrLine] = []
    words: list[PrintedOcrWord] = []
    word_seq = 0
    for line_index, raw in enumerate(raw_lines):
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
    started = time.perf_counter()
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
    rendered = render_page(
        pdf_path,
        page_number=page_ref.page_number,
        page_width_points=page_ref.width_points,
        page_height_points=page_ref.height_points,
        limits=limits,
        pdf_document=pdf_document,
    )
    emit_message(
        {
            "type": "page.rendered",
            "request_id": request_id,
            "page_number": page_ref.page_number,
            "width_pixels": rendered.width_pixels,
            "height_pixels": rendered.height_pixels,
            "effective_dpi": rendered.effective_dpi,
        }
    )

    primary_image, variant = prepare_primary(rendered.image)
    emit_message(
        {"type": "page.ocr_started", "request_id": request_id, "page_number": page_ref.page_number}
    )
    raw_lines = adapter.recognise(primary_image)
    fallback_used = False
    if (
        config.ocr_enable_grayscale_fallback
        and config.ocr_fallback_max_attempts >= 1
        and _raw_needs_fallback(raw_lines, config)
    ):
        fallback_image, variant = prepare_grayscale_fallback(rendered.image)
        raw_lines = adapter.recognise(fallback_image)
        fallback_used = True
        fallback_image.close()

    primary_image.close()
    rendered.image.close()

    lines, words = _build_contract_lines(
        raw_lines,
        page_number=page_ref.page_number,
        width_pixels=rendered.width_pixels,
        height_pixels=rendered.height_pixels,
        variant=variant,
        config=config,
    )
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
        fallback_used=fallback_used,
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
        warnings=warnings,
        duration_ms=duration_ms,
        peak_rss_mb=snap.rss_mb,
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
    try:
        config = _config_from_env_settings()
        adapter = PaddleOcrAdapter(config)
        adapter.load()
    except VisualOcrError as exc:
        emit_message(
            {
                "type": "error",
                "code": exc.code.value,
                "operation": exc.operation,
                "component": exc.failing_component,
                "exception_type": exc.exception_type,
            }
        )
        return 1
    except Exception as exc:
        _bounded_stderr(traceback.format_exc()[-_STDERR_MAX_BYTES:])
        emit_message(
            {
                "type": "error",
                "code": ErrorCode.OCR_MODEL_LOAD_FAILED.value,
                "exception_type": type(exc).__name__,
            }
        )
        return 1

    emit_message(
        {
            "type": "worker.ready",
            "paddleocr_version": adapter.paddleocr_version,
            "paddlepaddle_version": adapter.paddlepaddle_version,
            "word_box_key": adapter.schema.word_box_key if adapter.schema else None,
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
