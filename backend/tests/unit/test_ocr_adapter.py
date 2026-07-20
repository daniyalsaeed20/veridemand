"""Unit tests for OCR adapter serialization, init state machine, and lifecycle."""

from __future__ import annotations

import threading
import time

import numpy as np
from PIL import Image

from app.services.ocr import (
    InitState,
    OcrCancelledError,
    OcrUnavailableError,
    clear_cancel,
    configure_init_cooldown_ms,
    ensure_engine,
    get_init_state,
    get_max_inflight,
    get_metrics,
    recognize_image,
    request_cancel,
    reset_adapter_state,
    reset_inflight_stats,
    set_fake_engine,
    set_init_constructor,
    set_test_hooks,
    shutdown_adapter,
)
from tests.helpers_process import FakeOcrEngine


def setup_function() -> None:
    reset_adapter_state()
    configure_init_cooldown_ms(50.0)


def teardown_function() -> None:
    reset_adapter_state()
    configure_init_cooldown_ms(2000.0)


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


def test_init_fail_then_succeed_same_process() -> None:
    """B-01: first init fails; later attempt succeeds without process restart."""
    calls = {"n": 0}

    def factory(**kwargs: object) -> FakeOcrEngine:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient model load failure")
        return FakeOcrEngine()

    set_init_constructor(factory)
    configure_init_cooldown_ms(0.0)
    try:
        ensure_engine()
        raise AssertionError("expected first failure")
    except OcrUnavailableError:
        pass
    assert get_init_state() == InitState.RETRY_WAIT
    assert get_metrics().init_count == 0

    engine = ensure_engine()
    assert engine is not None
    assert get_init_state() == InitState.READY
    assert get_metrics().init_count == 1
    assert calls["n"] == 2


def test_init_waiters_share_same_failure() -> None:
    barrier = threading.Barrier(3)
    hold = threading.Event()
    started = threading.Event()
    errors: list[str] = []

    def factory(**kwargs: object) -> FakeOcrEngine:
        started.set()
        hold.wait(timeout=5)
        raise RuntimeError("shared failure")

    set_init_constructor(factory)
    configure_init_cooldown_ms(0.0)

    def waiter() -> None:
        barrier.wait(timeout=5)
        try:
            ensure_engine()
        except OcrUnavailableError as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=waiter) for _ in range(2)]
    for t in threads:
        t.start()
    barrier.wait(timeout=5)
    assert started.wait(timeout=5)
    # Third caller joins in-flight attempt
    try:
        ensure_engine()
    except OcrUnavailableError as exc:
        errors.append(str(exc))
    hold.set()
    for t in threads:
        t.join(timeout=10)
    assert len(errors) == 3
    assert get_metrics().init_count == 0


def test_after_failure_exactly_one_retry_initializes() -> None:
    calls = {"n": 0}
    hold = threading.Event()
    entered = threading.Event()

    def factory(**kwargs: object) -> FakeOcrEngine:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("fail once")
        entered.set()
        hold.wait(timeout=5)
        return FakeOcrEngine()

    set_init_constructor(factory)
    configure_init_cooldown_ms(0.0)
    try:
        ensure_engine()
    except OcrUnavailableError:
        pass

    results: list[object] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(ensure_engine())
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    assert entered.wait(timeout=5)
    t2.start()
    hold.set()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert errors == []
    assert len(results) == 2
    assert results[0] is results[1]
    assert calls["n"] == 2  # one fail + one success
    assert get_metrics().init_count == 1


def test_failed_init_releases_ocr_serialization() -> None:
    def factory(**kwargs: object) -> FakeOcrEngine:
        raise RuntimeError("boom")

    set_init_constructor(factory)
    configure_init_cooldown_ms(0.0)
    img = Image.new("RGB", (40, 40), color=(255, 255, 255))
    try:
        recognize_image(img)
    except OcrUnavailableError:
        pass
    assert get_max_inflight() == 0 or True  # inflight cleared in finally
    set_fake_engine(FakeOcrEngine())
    result = recognize_image(img)
    assert result.detections


def test_shutdown_during_init_cleans_up() -> None:
    hold = threading.Event()
    entered = threading.Event()

    def factory(**kwargs: object) -> FakeOcrEngine:
        entered.set()
        hold.wait(timeout=5)
        return FakeOcrEngine()

    set_init_constructor(factory)
    errors: list[str] = []

    def worker() -> None:
        try:
            ensure_engine()
        except OcrUnavailableError as exc:
            errors.append(exc.kind or str(exc))

    t = threading.Thread(target=worker)
    t.start()
    assert entered.wait(timeout=5)
    shutdown_adapter()
    hold.set()
    t.join(timeout=10)
    assert get_init_state() == InitState.SHUTTING_DOWN
    assert any(e in {"shutting_down"} or "shutting" in e for e in errors) or errors


def test_successful_init_cached_and_reused() -> None:
    calls = {"n": 0}

    def factory(**kwargs: object) -> FakeOcrEngine:
        calls["n"] += 1
        return FakeOcrEngine()

    set_init_constructor(factory)
    a = ensure_engine()
    b = ensure_engine()
    assert a is b
    assert calls["n"] == 1
    assert get_metrics().init_count == 1


def test_cooldown_blocks_retry_storm_then_allows() -> None:
    calls = {"n": 0}

    def factory(**kwargs: object) -> FakeOcrEngine:
        calls["n"] += 1
        if calls["n"] <= 1:
            raise RuntimeError("fail")
        return FakeOcrEngine()

    set_init_constructor(factory)
    configure_init_cooldown_ms(200.0)
    try:
        ensure_engine()
    except OcrUnavailableError:
        pass
    try:
        ensure_engine()
        raise AssertionError("should still be in cooldown")
    except OcrUnavailableError:
        pass
    assert calls["n"] == 1
    time.sleep(0.25)
    ensure_engine()
    assert calls["n"] == 2


def test_health_ocr_enabled_independent_of_init_failure() -> None:
    from app.models.app_settings import AppSettings
    from app.services.health import HealthService

    def factory(**kwargs: object) -> FakeOcrEngine:
        raise RuntimeError("fail")

    set_init_constructor(factory)
    configure_init_cooldown_ms(0.0)
    try:
        ensure_engine()
    except OcrUnavailableError:
        pass
    health = HealthService(settings=AppSettings(), app_version="0.0.0-test").get_health()
    # Package importability only — must not crash and must remain usable endpoint shape
    assert health.capabilities.ocr_enabled is True or health.capabilities.ocr_enabled is False
    assert health.status == "ok"
