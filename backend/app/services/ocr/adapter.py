"""Sole PaddleOCR adapter — the only production module allowed to import paddle*.

Lazy CPU initialization, process-wide single-worker serialization, and
application-neutral result conversion live here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np
from PIL import Image

from app.core.logging import get_logger
from app.services.ocr.model_paths import ensure_ocr_model_dir
from app.services.ocr.types import OcrAdapterMetrics, OcrDetection, OcrRawResult

logger = get_logger(__name__)

# Process-wide: at most one active OCR recognize in the application process.
_OCR_WORKER_LOCK = threading.RLock()
_INIT_LOCK = threading.Lock()

_engine: Any | None = None
_init_attempted = False
_init_error: str | None = None
_metrics = OcrAdapterMetrics()
_cancel_requested = threading.Event()

# Test instrumentation
_enter_hook: Callable[[], None] | None = None
_exit_hook: Callable[[], None] | None = None
_fault_hook: Callable[[str], None] | None = None
_fake_engine: Any | None = None

_inflight = 0
_max_inflight = 0
_inflight_lock = threading.Lock()


class OcrUnavailableError(Exception):
    """OCR dependencies or models are not available."""


class OcrCancelledError(Exception):
    """OCR operation cancelled (session deleted/expired)."""


class OcrEngineProtocol(Protocol):
    def ocr(self, img: Any, cls: bool = True) -> Any: ...


def get_ocr_worker_lock() -> threading.RLock:
    return _OCR_WORKER_LOCK


def get_metrics() -> OcrAdapterMetrics:
    return OcrAdapterMetrics(
        init_count=_metrics.init_count,
        recognize_count=_metrics.recognize_count,
        cancel_count=_metrics.cancel_count,
        error_count=_metrics.error_count,
        last_init_ms=_metrics.last_init_ms,
        last_recognize_ms=_metrics.last_recognize_ms,
    )


def reset_inflight_stats() -> None:
    global _inflight, _max_inflight
    with _inflight_lock:
        _inflight = 0
        _max_inflight = 0


def get_max_inflight() -> int:
    with _inflight_lock:
        return _max_inflight


def set_test_hooks(
    *,
    enter: Callable[[], None] | None = None,
    exit_hook: Callable[[], None] | None = None,
    fault: Callable[[str], None] | None = None,
) -> None:
    global _enter_hook, _exit_hook, _fault_hook
    _enter_hook = enter
    _exit_hook = exit_hook
    _fault_hook = fault


def set_fake_engine(engine: Any | None) -> None:
    """Inject a fake engine for unit tests (bypasses PaddleOCR)."""
    global _engine, _init_attempted, _init_error, _fake_engine
    with _INIT_LOCK:
        _fake_engine = engine
        if engine is not None:
            _engine = engine
            _init_attempted = True
            _init_error = None
        else:
            _engine = None
            _init_attempted = False
            _init_error = None


def reset_adapter_state() -> None:
    """Test helper: clear singleton engine and metrics."""
    global _engine, _init_attempted, _init_error, _fake_engine
    with _INIT_LOCK:
        _engine = None
        _init_attempted = False
        _init_error = None
        _fake_engine = None
        _metrics.init_count = 0
        _metrics.recognize_count = 0
        _metrics.cancel_count = 0
        _metrics.error_count = 0
        _metrics.last_init_ms = None
        _metrics.last_recognize_ms = None
    _cancel_requested.clear()
    reset_inflight_stats()
    set_test_hooks()


def request_cancel() -> None:
    _cancel_requested.set()
    _metrics.cancel_count += 1


def clear_cancel() -> None:
    _cancel_requested.clear()


def paddleocr_importable() -> bool:
    """True when paddle packages are installed (does not load models)."""
    import importlib.util

    return (
        importlib.util.find_spec("paddle") is not None
        and importlib.util.find_spec("paddleocr") is not None
    )


def models_apparently_available() -> bool:
    """Best-effort check: cache dir exists (models may still download on first use)."""
    try:
        path = ensure_ocr_model_dir()
        return path.is_dir()
    except OSError:
        return False


def ocr_capability_enabled() -> bool:
    """True when paddle packages import; models may still lazy-load later."""
    return paddleocr_importable()


def ensure_engine() -> Any:
    """Lazy-initialize the PaddleOCR engine once (CPU)."""
    global _engine, _init_attempted, _init_error
    if _engine is not None:
        return _engine
    with _INIT_LOCK:
        if _engine is not None:
            return _engine
        if _fake_engine is not None:
            _engine = _fake_engine
            _init_attempted = True
            return _engine
        if _init_attempted and _init_error is not None:
            raise OcrUnavailableError(_init_error)
        _init_attempted = True
        started = time.perf_counter()
        try:
            model_dir = ensure_ocr_model_dir()
            # Direct paddleocr import only in this module.
            from paddleocr import PaddleOCR

            # Avoid writing into the repository; use external cache.
            # PaddleOCR 2.7.3 accepts det/rec/cls model dirs via download defaults;
            # set HOME-like env for paddle model hub via det_model_dir parent.
            engine = PaddleOCR(
                use_angle_cls=True,
                lang="en",
                use_gpu=False,
                show_log=False,
                det_model_dir=str(model_dir / "det"),
                rec_model_dir=str(model_dir / "rec"),
                cls_model_dir=str(model_dir / "cls"),
            )
            _engine = engine
            _init_error = None
            _metrics.init_count += 1
            _metrics.last_init_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "OCR engine initialized",
                extra={"extra_fields": {"init_ms": round(_metrics.last_init_ms, 1)}},
            )
            return _engine
        except Exception as exc:  # noqa: BLE001
            _init_error = "OCR engine initialization failed."
            _metrics.error_count += 1
            logger.exception("OCR engine initialization failed")
            raise OcrUnavailableError(_init_error) from exc


def recognize_image(image: Image.Image) -> OcrRawResult:
    """Run OCR under the single-worker lock. Does not hold PDFium or session locks."""
    global _inflight, _max_inflight
    if _cancel_requested.is_set():
        raise OcrCancelledError("OCR cancelled before start.")

    with _OCR_WORKER_LOCK:
        with _inflight_lock:
            _inflight += 1
            if _inflight > _max_inflight:
                _max_inflight = _inflight
        if _enter_hook is not None:
            _enter_hook()
        started = time.perf_counter()
        try:
            if _fault_hook is not None:
                _fault_hook("recognize")
            if _cancel_requested.is_set():
                raise OcrCancelledError("OCR cancelled.")
            engine = ensure_engine()
            rgb = image.convert("RGB")
            arr = np.asarray(rgb)
            # Classic PaddleOCR 2.7 API
            raw = engine.ocr(arr, cls=True)
            if _cancel_requested.is_set():
                raise OcrCancelledError("OCR cancelled after inference.")
            detections, warnings = _parse_paddle_result(raw)
            elapsed = (time.perf_counter() - started) * 1000.0
            _metrics.recognize_count += 1
            _metrics.last_recognize_ms = elapsed
            return OcrRawResult(
                detections=detections,
                warnings=warnings,
                elapsed_ms=elapsed,
            )
        except OcrCancelledError:
            raise
        except OcrUnavailableError:
            _metrics.error_count += 1
            raise
        except Exception as exc:  # noqa: BLE001
            _metrics.error_count += 1
            logger.exception("OCR recognition failed")
            raise OcrUnavailableError("OCR recognition failed.") from exc
        finally:
            with _inflight_lock:
                _inflight -= 1
            if _exit_hook is not None:
                _exit_hook()


def _parse_paddle_result(result: Any) -> tuple[list[OcrDetection], list[str]]:
    warnings: list[str] = []
    detections: list[OcrDetection] = []
    if result is None:
        return detections, ["ocr_empty_result"]

    # Classic shape: [ [ [box], (text, conf) ], ... ] or wrapped in one more list
    pages = result
    if isinstance(result, list) and result and isinstance(result[0], list):
        # Could be page list or line list
        first = result[0]
        if first and isinstance(first, list) and first and isinstance(first[0], list | tuple):
            # Heuristic: if first[0] looks like a box (list of points), it's lines
            sample = first[0]
            if (
                isinstance(sample, list | tuple)
                and len(sample) >= 2
                and isinstance(sample[0], list | tuple)
                and len(sample[0]) == 2
                and isinstance(sample[0][0], int | float)
            ):
                pages = [result]

    if not isinstance(pages, list):
        warnings.append("ocr_malformed_result")
        return detections, warnings

    for page in pages:
        if page is None:
            continue
        if not isinstance(page, list):
            warnings.append("ocr_malformed_page")
            continue
        for item in page:
            parsed = _parse_line(item)
            if parsed is None:
                warnings.append("ocr_skipped_malformed_line")
                continue
            detections.append(parsed)
    return detections, warnings


def _parse_line(item: Any) -> OcrDetection | None:
    try:
        if not isinstance(item, list | tuple) or len(item) < 2:
            return None
        box, meta = item[0], item[1]
        if not isinstance(box, list | tuple) or len(box) < 3:
            return None
        polygon: list[tuple[float, float]] = []
        for pt in box:
            if not isinstance(pt, list | tuple) or len(pt) < 2:
                return None
            polygon.append((float(pt[0]), float(pt[1])))
        if isinstance(meta, list | tuple) and len(meta) >= 2:
            text = str(meta[0] or "")
            conf = float(meta[1])
        elif isinstance(meta, dict):
            text = str(meta.get("text") or meta.get("transcription") or "")
            conf = float(meta.get("confidence") or meta.get("score") or 0.0)
        else:
            return None
        conf = max(0.0, min(1.0, conf))
        return OcrDetection(text=text, confidence=conf, polygon_px=polygon)
    except (TypeError, ValueError):
        return None
