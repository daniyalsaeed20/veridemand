"""OCR service package — sole production boundary for PaddleOCR."""

from app.services.ocr.adapter import (
    OcrCancelledError,
    OcrUnavailableError,
    clear_cancel,
    ensure_engine,
    get_max_inflight,
    get_metrics,
    get_ocr_worker_lock,
    ocr_capability_enabled,
    recognize_image,
    request_cancel,
    reset_adapter_state,
    reset_inflight_stats,
    set_fake_engine,
    set_test_hooks,
)
from app.services.ocr.types import OcrDetection, OcrRawResult

__all__ = [
    "OcrCancelledError",
    "OcrDetection",
    "OcrRawResult",
    "OcrUnavailableError",
    "clear_cancel",
    "ensure_engine",
    "get_max_inflight",
    "get_metrics",
    "get_ocr_worker_lock",
    "ocr_capability_enabled",
    "recognize_image",
    "request_cancel",
    "reset_adapter_state",
    "reset_inflight_stats",
    "set_fake_engine",
    "set_test_hooks",
]
