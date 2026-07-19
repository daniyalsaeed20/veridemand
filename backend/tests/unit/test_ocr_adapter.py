"""Unit tests for OCR adapter serialization and lifecycle."""

from __future__ import annotations

import threading
import time

import numpy as np
from PIL import Image

from app.services.ocr import (
    OcrCancelledError,
    clear_cancel,
    get_max_inflight,
    recognize_image,
    request_cancel,
    reset_adapter_state,
    reset_inflight_stats,
    set_fake_engine,
    set_test_hooks,
)
from tests.helpers_process import FakeOcrEngine


def setup_function() -> None:
    reset_adapter_state()


def teardown_function() -> None:
    reset_adapter_state()


def test_lazy_fake_engine_recognize() -> None:
    engine = FakeOcrEngine()
    set_fake_engine(engine)
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    result = recognize_image(img)
    assert engine.calls == 1
    assert len(result.detections) == 2
    assert result.detections[0].text == "Hello"


def test_single_worker_serialization() -> None:
    engine = FakeOcrEngine()
    set_fake_engine(engine)
    reset_inflight_stats()
    hold = threading.Event()
    first_entered = threading.Event()

    def on_enter() -> None:
        first_entered.set()
        hold.wait(timeout=5)

    set_test_hooks(enter=on_enter)
    results: list[int] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            img = Image.new("RGB", (100, 100), color=(255, 255, 255))
            recognize_image(img)
            results.append(1)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    assert first_entered.wait(timeout=5)
    t2.start()
    time.sleep(0.15)
    assert get_max_inflight() == 1
    hold.set()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert errors == []
    assert sum(results) == 2
    assert get_max_inflight() == 1
    assert engine.calls == 2


def test_cancel_releases_worker() -> None:
    class BlockingEngine:
        def ocr(self, img, cls: bool = True):
            request_cancel()
            raise RuntimeError("should not finish")

    set_fake_engine(BlockingEngine())
    clear_cancel()
    request_cancel()
    img = Image.new("RGB", (50, 50), color=(255, 255, 255))
    try:
        recognize_image(img)
        raise AssertionError("expected cancel")
    except OcrCancelledError:
        pass
    finally:
        clear_cancel()


def test_exception_releases_worker_lock() -> None:
    class BoomEngine:
        def ocr(self, img, cls: bool = True):
            raise RuntimeError("boom")

    set_fake_engine(BoomEngine())
    img = Image.new("RGB", (50, 50), color=(255, 255, 255))
    try:
        recognize_image(img)
    except Exception:
        pass
    # Second call should acquire lock again (not deadlocked)
    set_fake_engine(FakeOcrEngine())
    clear_cancel()
    result = recognize_image(img)
    assert result.detections


def test_malformed_engine_response() -> None:
    class BadEngine:
        def ocr(self, img, cls: bool = True):
            return "not-a-list"

    set_fake_engine(BadEngine())
    img = Image.fromarray(np.zeros((40, 40, 3), dtype=np.uint8))
    result = recognize_image(img)
    assert result.detections == []
    assert "ocr_malformed_result" in result.warnings or result.detections == []
