"""Sole PaddleOCR adapter — the only production module allowed to import paddle*.

Lazy CPU initialization with a retriable state machine, process-wide
single-worker serialization, and application-neutral result conversion.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import StrEnum
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
_metrics = OcrAdapterMetrics()

# Process-global cancel (shutdown / legacy); prefer per-session Events via recognize_image.
_cancel_requested = threading.Event()

# Test instrumentation
_enter_hook: Callable[[], None] | None = None
_exit_hook: Callable[[], None] | None = None
_fault_hook: Callable[[str], None] | None = None
_fake_engine: Any | None = None
_init_constructor: Callable[..., Any] | None = None  # test override for PaddleOCR()

_inflight = 0
_max_inflight = 0
_inflight_lock = threading.Lock()

# Init state machine (B-01)
_init_cooldown_ms = 2000.0
_retry_ready_at: float = 0.0
_last_init_error: str | None = None
_last_init_kind: str | None = None  # packages_missing | model_cache | transient | shutting_down


class InitState(StrEnum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    RETRY_WAIT = "retry_wait"
    SHUTTING_DOWN = "shutting_down"


_init_state = InitState.UNINITIALIZED

# Shared in-flight attempt: waiters observe the same result.
_init_attempt_event: threading.Event | None = None
_init_attempt_error: BaseException | None = None
_init_attempt_engine: Any | None = None


class OcrUnavailableError(Exception):
    """OCR dependencies or models are not available."""

    def __init__(self, message: str, *, kind: str | None = None) -> None:
        super().__init__(message)
        self.kind = kind


class OcrCancelledError(Exception):
    """OCR operation cancelled (session deleted/expired)."""


class OcrEngineProtocol(Protocol):
    def ocr(self, img: Any, cls: bool = True) -> Any: ...


def get_ocr_worker_lock() -> threading.RLock:
    return _OCR_WORKER_LOCK


def get_init_state() -> InitState:
    with _INIT_LOCK:
        return _init_state


def configure_init_cooldown_ms(ms: float) -> None:
    """Set bounded retry cooldown (from AppSettings at process start or tests)."""
    global _init_cooldown_ms
    _init_cooldown_ms = max(0.0, float(ms))


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


def set_init_constructor(factory: Callable[..., Any] | None) -> None:
    """Tests: replace PaddleOCR constructor (or clear)."""
    global _init_constructor
    with _INIT_LOCK:
        _init_constructor = factory


def set_fake_engine(engine: Any | None) -> None:
    """Inject a fake engine for unit tests (bypasses PaddleOCR)."""
    global _engine, _fake_engine, _init_state, _last_init_error, _retry_ready_at
    with _INIT_LOCK:
        _fake_engine = engine
        if engine is not None:
            _engine = engine
            _init_state = InitState.READY
            _last_init_error = None
            _retry_ready_at = 0.0
        else:
            _engine = None
            _init_state = InitState.UNINITIALIZED
            _last_init_error = None
            _retry_ready_at = 0.0


def reset_adapter_state() -> None:
    """Test helper: clear singleton engine, state machine, and metrics."""
    global _engine, _fake_engine, _init_state, _last_init_error, _last_init_kind
    global _retry_ready_at, _init_attempt_event, _init_attempt_error, _init_attempt_engine
    global _init_constructor
    with _INIT_LOCK:
        _engine = None
        _fake_engine = None
        _init_constructor = None
        _init_state = InitState.UNINITIALIZED
        _last_init_error = None
        _last_init_kind = None
        _retry_ready_at = 0.0
        if _init_attempt_event is not None:
            _init_attempt_event.set()
        _init_attempt_event = None
        _init_attempt_error = None
        _init_attempt_engine = None
        _metrics.init_count = 0
        _metrics.recognize_count = 0
        _metrics.cancel_count = 0
        _metrics.error_count = 0
        _metrics.last_init_ms = None
        _metrics.last_recognize_ms = None
    _cancel_requested.clear()
    reset_inflight_stats()
    set_test_hooks()


def shutdown_adapter() -> None:
    """Application lifespan: mark shutting down, wake waiters, drop engine."""
    global _engine, _init_state, _init_attempt_event, _init_attempt_error, _init_attempt_engine
    with _INIT_LOCK:
        _init_state = InitState.SHUTTING_DOWN
        _engine = None
        _init_attempt_error = OcrUnavailableError(
            "OCR adapter is shutting down.",
            kind="shutting_down",
        )
        if _init_attempt_event is not None:
            _init_attempt_event.set()
        _init_attempt_event = None
        _init_attempt_engine = None
    _cancel_requested.set()
    logger.info("OCR adapter shut down")


def request_cancel() -> None:
    """Process-global cancel (prefer per-session Event passed to recognize_image)."""
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
    """Lazy-initialize the PaddleOCR engine (CPU) with retriable state machine."""
    global _engine, _init_state, _retry_ready_at, _last_init_error, _last_init_kind
    global _init_attempt_event, _init_attempt_error, _init_attempt_engine

    if _engine is not None and _init_state == InitState.READY:
        return _engine

    # Fast path under lock: join in-flight attempt or start a new one.
    while True:
        with _INIT_LOCK:
            if _init_state == InitState.SHUTTING_DOWN:
                raise OcrUnavailableError(
                    "OCR adapter is shutting down.",
                    kind="shutting_down",
                )
            if _engine is not None and _init_state == InitState.READY:
                return _engine
            if _fake_engine is not None:
                _engine = _fake_engine
                _init_state = InitState.READY
                _last_init_error = None
                return _engine

            if _init_state == InitState.INITIALIZING and _init_attempt_event is not None:
                wait_event = _init_attempt_event
                leader = False
            elif _init_state == InitState.RETRY_WAIT and time.monotonic() < _retry_ready_at:
                err = _last_init_error or "OCR engine initialization failed."
                kind = _last_init_kind
                # Still in cooldown — raise same failure without starting a new attempt
                raise OcrUnavailableError(err, kind=kind)
            else:
                # Start a fresh attempt
                _init_state = InitState.INITIALIZING
                _init_attempt_event = threading.Event()
                _init_attempt_error = None
                _init_attempt_engine = None
                wait_event = None
                leader = True

        if not leader:
            assert wait_event is not None
            wait_event.wait(timeout=600.0)
            with _INIT_LOCK:
                if _init_attempt_engine is not None:
                    return _init_attempt_engine
                if _engine is not None and _init_state == InitState.READY:
                    return _engine
                attempt_err = _init_attempt_error
                if attempt_err is not None:
                    if isinstance(attempt_err, OcrUnavailableError):
                        raise attempt_err
                    raise OcrUnavailableError(
                        _last_init_error or "OCR engine initialization failed.",
                        kind=_last_init_kind,
                    ) from attempt_err
                # Spurious wake / cleared — retry loop
                continue

        # Leader performs construction outside INIT_LOCK so waiters can attach,
        # but still typically under OCR worker lock via recognize_image.
        started = time.perf_counter()
        engine: Any | None = None
        failure: BaseException | None = None
        fail_kind = "transient"
        fail_msg = "OCR engine initialization failed."
        try:
            if _fault_hook is not None:
                _fault_hook("init")
            if not paddleocr_importable() and _init_constructor is None:
                fail_kind = "packages_missing"
                fail_msg = "OCR packages are not installed."
                raise OcrUnavailableError(fail_msg, kind=fail_kind)

            model_dir = ensure_ocr_model_dir()
            if _init_constructor is not None:
                factory = _init_constructor
            else:
                from paddleocr import PaddleOCR

                factory = PaddleOCR

            engine = factory(
                use_angle_cls=True,
                lang="en",
                use_gpu=False,
                show_log=False,
                det_model_dir=str(model_dir / "det"),
                rec_model_dir=str(model_dir / "rec"),
                cls_model_dir=str(model_dir / "cls"),
            )
        except OcrUnavailableError as exc:
            failure = exc
            fail_kind = exc.kind or fail_kind
            fail_msg = str(exc)
        except Exception as exc:  # noqa: BLE001
            failure = exc
            # Safe operational kind only — never include paths
            msg = str(exc).lower()
            if "not found" in msg or "no such file" in msg:
                fail_kind = "model_cache"
            else:
                fail_kind = "transient"
            fail_msg = "OCR engine initialization failed."
            logger.exception(
                "OCR engine initialization failed",
                extra={"extra_fields": {"kind": fail_kind}},
            )

        with _INIT_LOCK:
            if _init_state == InitState.SHUTTING_DOWN:
                _init_attempt_error = OcrUnavailableError(
                    "OCR adapter is shutting down.",
                    kind="shutting_down",
                )
                if _init_attempt_event is not None:
                    _init_attempt_event.set()
                raise OcrUnavailableError(
                    "OCR adapter is shutting down.",
                    kind="shutting_down",
                )

            if failure is not None:
                _engine = None  # never publish partial
                _init_state = InitState.RETRY_WAIT
                _retry_ready_at = time.monotonic() + (_init_cooldown_ms / 1000.0)
                _last_init_error = fail_msg
                _last_init_kind = fail_kind
                _metrics.error_count += 1
                wrapped = (
                    failure
                    if isinstance(failure, OcrUnavailableError)
                    else OcrUnavailableError(fail_msg, kind=fail_kind)
                )
                if not isinstance(failure, OcrUnavailableError):
                    try:
                        wrapped.__cause__ = failure
                    except Exception:  # noqa: BLE001
                        pass
                _init_attempt_error = wrapped
                _init_attempt_engine = None
                event = _init_attempt_event
                _init_attempt_event = None
                if event is not None:
                    event.set()
                raise wrapped

            # Success — publish only now
            _engine = engine
            _init_state = InitState.READY
            _last_init_error = None
            _last_init_kind = None
            _retry_ready_at = 0.0
            _metrics.init_count += 1
            _metrics.last_init_ms = (time.perf_counter() - started) * 1000.0
            _init_attempt_engine = engine
            _init_attempt_error = None
            event = _init_attempt_event
            _init_attempt_event = None
            if event is not None:
                event.set()
            logger.info(
                "OCR engine initialized",
                extra={"extra_fields": {"init_ms": round(_metrics.last_init_ms, 1)}},
            )
            return engine


def recognize_image(
    image: Image.Image,
    *,
    cancel_event: threading.Event | None = None,
) -> OcrRawResult:
    """Run OCR under the single-worker lock. Does not hold PDFium or session locks.

    A running engine.ocr(...) may finish after cancel; callers must discard late results.
    """
    global _inflight, _max_inflight

    def _cancelled() -> bool:
        if _cancel_requested.is_set():
            return True
        if cancel_event is not None and cancel_event.is_set():
            return True
        return False

    if _cancelled():
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
            if _cancelled():
                raise OcrCancelledError("OCR cancelled.")
            engine = ensure_engine()
            rgb = image.convert("RGB")
            arr = np.asarray(rgb)
            raw = engine.ocr(arr, cls=True)
            if _cancelled():
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

    pages = result
    if isinstance(result, list) and result and isinstance(result[0], list):
        first = result[0]
        if first and isinstance(first, list) and first and isinstance(first[0], list | tuple):
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
