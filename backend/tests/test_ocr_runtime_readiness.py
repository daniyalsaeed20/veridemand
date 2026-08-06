"""OCR runtime readiness state, taxonomy, retry, and health semantics."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.app.contracts.ocr_runtime import (
    OcrRuntimeErrorCode,
    OcrRuntimeStage,
    OcrRuntimeState,
)
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.ocr_readiness import (
    classify_exception,
    is_retryable,
    operator_hint_for,
    sanitize_technical_detail,
    user_message_for,
)
from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.main import create_app
from backend.app.settings.config import Settings

_API = "/api/v1"


def test_initial_not_started_status() -> None:
    manager = OcrWorkerManager(Settings(ocr_enabled=True))
    status = manager.runtime_status()
    assert status.state is OcrRuntimeState.NOT_STARTED
    assert status.ready is False
    assert status.retryable is True
    assert status.attempt_number == 0


def test_disabled_status_is_not_starting() -> None:
    manager = OcrWorkerManager(Settings(ocr_enabled=False))
    status = manager.runtime_status()
    assert status.state is OcrRuntimeState.DISABLED
    assert status.error_code is OcrRuntimeErrorCode.OCR_DISABLED
    assert status.retryable is False
    assert "disabled" in (status.user_message or "").lower()
    assert "starting" not in (status.user_message or "").lower()


@pytest.mark.parametrize(
    ("code", "restart_required", "expected"),
    [
        (OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED, False, True),
        (OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED, True, False),
        (OcrRuntimeErrorCode.OCR_WARMUP_FAILED, False, True),
        (OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT, False, True),
        (OcrRuntimeErrorCode.OCR_OUT_OF_MEMORY, False, True),
        (OcrRuntimeErrorCode.OCR_DISABLED, False, False),
        (OcrRuntimeErrorCode.OCR_MODELS_MISSING, False, False),
        (OcrRuntimeErrorCode.OCR_MODEL_INTEGRITY_FAILED, False, False),
        (OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED, False, False),
        (OcrRuntimeErrorCode.OCR_CONFIGURATION_INVALID, False, False),
    ],
)
def test_retryable_classification(
    code: OcrRuntimeErrorCode, restart_required: bool, expected: bool
) -> None:
    assert is_retryable(code, restart_required=restart_required) is expected


def test_windows_dll_mapping() -> None:
    code, detail = classify_exception(OSError("Error loading shm.dll from torch"))
    assert code is OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED
    assert detail is not None
    assert "shm.dll" in detail.lower() or "oserror" in detail.lower()
    hint = operator_hint_for(code, restart_required=True)
    assert "pnpm dev:ocr" in hint
    assert "restart" in hint.lower() or "Stop" in hint


def test_import_oom_timeout_warmup_mappings() -> None:
    assert (
        classify_exception(ImportError("No module named paddle"), operation="import_paddle")[0]
        is OcrRuntimeErrorCode.OCR_DEPENDENCY_IMPORT_FAILED
    )
    assert classify_exception(MemoryError("oom"))[0] is OcrRuntimeErrorCode.OCR_OUT_OF_MEMORY
    assert (
        classify_exception(RuntimeError("warm-up boom"), operation="warmup")[0]
        is OcrRuntimeErrorCode.OCR_WARMUP_FAILED
    )
    assert (
        classify_exception(TimeoutError("OCR worker startup timed out."), operation="await_ready")[
            0
        ]
        is OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT
    )
    assert (
        classify_exception(FileNotFoundError("missing"), operation="resolve_model_dirs")[0]
        is OcrRuntimeErrorCode.OCR_MODELS_MISSING
    )


def test_sanitize_strips_paths_and_secrets() -> None:
    raw = r"failed at C:\Users\secret\models\foo key=abc API_KEY=sk-live-123"
    cleaned = sanitize_technical_detail(raw)
    assert cleaned is not None
    assert "Users" not in cleaned
    assert "sk-live" not in cleaned
    assert "<path>" in cleaned or "redacted" in cleaned.lower()


def test_stage_transitions_and_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = OcrWorkerManager(Settings(ocr_enabled=True, ocr_worker_startup_timeout_seconds=5.0))

    async def _fake_start_locked() -> None:
        manager._transition(
            state=OcrRuntimeState.LOADING_DETECTOR,
            stage=OcrRuntimeStage.LOADING_DETECTOR,
            user_message="Printed OCR is starting",
        )
        assert manager.runtime_status().stage_index == 3
        manager._transition(
            state=OcrRuntimeState.LOADING_RECOGNIZER,
            stage=OcrRuntimeStage.LOADING_RECOGNIZER,
            user_message="Printed OCR is starting",
        )
        assert manager.runtime_status().stage_index == 4
        manager._transition(
            state=OcrRuntimeState.WARMING_UP,
            stage=OcrRuntimeStage.WARMING_UP,
            user_message="Printed OCR is starting",
        )
        assert manager.runtime_status().stage_index == 5
        manager._mark_ready()

    monkeypatch.setattr(manager, "_start_locked", _fake_start_locked)
    status = asyncio.run(manager.ensure_started())
    assert status.state is OcrRuntimeState.READY
    assert status.attempt_number == 1
    assert status.attempt_id is not None
    assert manager._state.ready is True


def test_detector_failure_and_retry_success(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = OcrWorkerManager(Settings(ocr_enabled=True))
    calls = {"n": 0}

    async def _fake_start_locked() -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            manager._mark_failed(
                OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED,
                technical_detail="detector boom",
            )
            from backend.app.contracts.errors import ErrorCode

            raise VisualOcrError(
                ErrorCode.OCR_WORKER_START_FAILED,
                "OCR worker reported startup failure.",
                operation="await_ready",
                failing_component="OcrWorkerManager",
            )
        manager._mark_ready()

    monkeypatch.setattr(manager, "_start_locked", _fake_start_locked)
    monkeypatch.setattr(manager, "_terminate_locked", AsyncMock())

    with pytest.raises(VisualOcrError):
        asyncio.run(manager.ensure_started())
    failed = manager.runtime_status()
    assert failed.state is OcrRuntimeState.FAILED
    assert failed.error_code is OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED
    assert failed.retryable is True
    first_attempt = failed.attempt_id
    first_number = failed.attempt_number

    async def _retry_and_wait() -> None:
        await manager.retry_initialization()
        # Drain the background retry task.
        await asyncio.sleep(0.05)
        for _ in range(50):
            if manager._state.ready:
                return
            await asyncio.sleep(0.02)

    asyncio.run(_retry_and_wait())
    ready = manager.runtime_status()
    assert ready.state is OcrRuntimeState.READY
    assert manager._state.ready is True
    assert ready.attempt_number > first_number
    assert ready.attempt_id != first_attempt
    assert calls["n"] == 2


def test_duplicate_retry_suppressed_while_starting(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = OcrWorkerManager(Settings(ocr_enabled=True))
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    async def _fake_start_locked() -> None:
        calls["n"] += 1
        started.set()
        await release.wait()
        manager._mark_ready()

    monkeypatch.setattr(manager, "_start_locked", _fake_start_locked)
    monkeypatch.setattr(manager, "_terminate_locked", AsyncMock())

    async def _run() -> None:
        task = asyncio.create_task(manager.ensure_started())
        await started.wait()
        first = await manager.retry_initialization()
        second = await manager.retry_initialization()
        assert first.attempt_id == second.attempt_id
        assert calls["n"] == 1
        release.set()
        await task

    asyncio.run(_run())


def test_non_retryable_missing_models(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = OcrWorkerManager(Settings(ocr_enabled=True))

    async def _fail() -> None:
        manager._mark_failed(OcrRuntimeErrorCode.OCR_MODELS_MISSING, technical_detail="missing")
        from backend.app.contracts.errors import ErrorCode

        raise VisualOcrError(
            ErrorCode.OCR_WORKER_START_FAILED,
            "missing",
            operation="await_ready",
            failing_component="OcrWorkerManager",
        )

    monkeypatch.setattr(manager, "_start_locked", _fail)
    with pytest.raises(VisualOcrError):
        asyncio.run(manager.ensure_started())
    status = manager.runtime_status()
    assert status.retryable is False
    assert "missing" in (status.user_message or "").lower()
    after = asyncio.run(manager.retry_initialization())
    assert after.state is OcrRuntimeState.FAILED
    assert after.retryable is False


@pytest.fixture
def readiness_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("VERIDEMAND_SKIP_OCR_WORKER", "1")
    settings = Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=True,
        render_concurrency=1,
        ocr_concurrency=1,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_health_live_during_ocr_failure(readiness_client: TestClient) -> None:
    live = readiness_client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "ok"

    ready = readiness_client.get("/health/ready")
    assert ready.status_code == 503
    body = ready.json()
    assert body["status"] == "not_ready"
    assert body["ocr_runtime"] is not None
    assert body["ocr_runtime"]["ready"] is False
    assert "starting or unavailable" not in str(body).lower()


def test_paddle_check_prefers_worker_and_never_500_on_import_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API-process paddle import must not turn /health/ready into HTTP 500."""
    from backend.app.contracts.health import CheckState
    from backend.app.contracts.ocr_runtime import OcrComponentStatus, OcrRuntimeStatus
    from backend.app.health.service import HealthService

    settings = Settings(temp_root=tmp_path / "temp", ocr_enabled=True)
    service = HealthService(settings)

    class _Worker:
        ready = False

        def runtime_status(self) -> OcrRuntimeStatus:
            return OcrRuntimeStatus(
                state=OcrRuntimeState.FAILED,
                ready=False,
                retryable=True,
                error_code=OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED,
                user_message="Printed OCR dependency failed to load.",
                operator_hint="Use .venv-ocr.",
                technical_detail="OSError: shm.dll",
                detector_status=OcrComponentStatus.FAILED,
                recognizer_status=OcrComponentStatus.FAILED,
                model_verification_status=OcrComponentStatus.PENDING,
            )

    service.attach_runtime(
        coordinator=type("C", (), {"running": True})(),
        cleanup_worker=type("W", (), {"running": True})(),
        job_queue=type("Q", (), {"closed": False})(),
        ocr_worker_manager=_Worker(),
    )

    check = service._check_paddle_ocr()
    assert check.status is CheckState.FAIL
    assert check.message is not None
    assert "Printed OCR dependency failed to load" in check.message

    # Without worker, OSError on import is FAIL not an unhandled exception.
    service2 = HealthService(settings)
    import builtins

    real_import = builtins.__import__

    def _fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"paddle", "paddleocr"} or name.startswith("paddle"):
            raise OSError(127, "Error loading shm.dll")
        return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    check2 = service2._check_paddle_ocr()
    assert check2.status is CheckState.FAIL
    assert check2.message is not None
    assert "OCR-only" in check2.message or "venv-ocr" in check2.message


def test_retry_endpoint_and_session_preserved(
    readiness_client: TestClient, uploads_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = readiness_client.post(f"{_API}/sessions")
    assert created.status_code == 201
    session_id = created.json()["session_id"]

    files = [
        (
            "files",
            (
                "valid_single_page.pdf",
                (uploads_dir / "valid_single_page.pdf").read_bytes(),
                "application/pdf",
            ),
        )
    ]
    upload = readiness_client.post(f"{_API}/sessions/{session_id}/documents", files=files)
    assert upload.status_code == 201

    manager = cast(Any, readiness_client.app).state.ocr_worker_manager
    assert isinstance(manager, OcrWorkerManager)
    manager._mark_failed(OcrRuntimeErrorCode.OCR_WARMUP_FAILED, technical_detail="warmup")

    async def _ok() -> None:
        manager._mark_ready()

    monkeypatch.setattr(manager, "_start_locked", _ok)
    monkeypatch.setattr(manager, "_terminate_locked", AsyncMock())

    retry = readiness_client.post(f"{_API}/runtime/ocr/retry")
    assert retry.status_code == 202
    payload = retry.json()
    assert "attempt_id" in payload
    assert payload["status_url"] == "/health/ready"

    # Session documents remain.
    snap = readiness_client.get(f"{_API}/sessions/{session_id}")
    assert snap.status_code == 200
    assert len(snap.json()["documents"]) == 1


def test_dll_env_conflict_is_restart_required_not_retryable() -> None:
    from backend.app.contracts.ocr_runtime import OcrPythonEnvironmentKind
    from backend.app.extraction.visual.ocr_environment import OcrEnvironmentDiagnostics
    from backend.app.extraction.visual.ocr_readiness import restart_required_for

    mixed = OcrEnvironmentDiagnostics(
        kind=OcrPythonEnvironmentKind.MIXED,
        executable_environment=".venv",
        torch_present=True,
        torchvision_present=False,
        paddle_present=True,
        environment_conflict=True,
    )
    assert (
        restart_required_for(
            OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED,
            technical_detail="OSError: shm.dll",
            diagnostics=mixed,
        )
        is True
    )
    assert is_retryable(OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED, restart_required=True) is False

    clean = OcrEnvironmentDiagnostics(
        kind=OcrPythonEnvironmentKind.OCR,
        executable_environment=".venv-ocr",
        torch_present=False,
        torchvision_present=False,
        paddle_present=True,
        environment_conflict=False,
    )
    assert (
        restart_required_for(
            OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED,
            technical_detail="OSError: transient dll load failed",
            diagnostics=clean,
        )
        is False
    )


def test_retry_rejected_when_restart_required(readiness_client: TestClient) -> None:
    manager = cast(Any, readiness_client.app).state.ocr_worker_manager
    assert isinstance(manager, OcrWorkerManager)
    manager._mark_failed(
        OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED,
        technical_detail="OSError: shm.dll from torch",
        restart_required=True,
    )
    status = manager.runtime_status()
    assert status.retryable is False
    assert status.restart_required is True
    assert status.recovery_action.value == "restart_backend_in_ocr_environment"
    attempt = status.attempt_number

    retry = readiness_client.post(f"{_API}/runtime/ocr/retry")
    assert retry.status_code == 400
    body = retry.json()
    assert body["error"]["code"] == "ocr_retry_not_allowed"
    assert body["error"]["details"]["restart_required"] is True
    assert manager.runtime_status().attempt_number == attempt


def test_retry_rejected_when_not_retryable(readiness_client: TestClient) -> None:
    manager = cast(Any, readiness_client.app).state.ocr_worker_manager
    assert isinstance(manager, OcrWorkerManager)
    manager._mark_failed(OcrRuntimeErrorCode.OCR_MODELS_MISSING, technical_detail="missing")
    response = readiness_client.post(f"{_API}/runtime/ocr/retry")
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "ocr_retry_not_allowed"
    assert body["error"]["details"]["retryable"] is False


def test_user_messages_are_operator_safe() -> None:
    for code in OcrRuntimeErrorCode:
        if code is OcrRuntimeErrorCode.BACKEND_UNREACHABLE:
            continue
        msg = user_message_for(code)
        assert msg
        assert "traceback" not in msg.lower()
        assert "c:\\" not in msg.lower()


def test_production_rejects_test_injection() -> None:
    with pytest.raises(ValueError, match="test injection"):
        Settings(app_env="production", ocr_test_fail_once_code="ocr_dll_load_failed")


def test_attempt_timestamps_are_timezone_aware(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = OcrWorkerManager(Settings(ocr_enabled=True))

    async def _ok() -> None:
        manager._mark_ready()

    monkeypatch.setattr(manager, "_start_locked", _ok)
    status = asyncio.run(manager.ensure_started())
    assert status.attempt_started_at is not None
    assert status.attempt_started_at.tzinfo is not None
    assert status.last_transition_at is not None
    assert isinstance(status.last_transition_at, datetime)
    assert status.last_transition_at.tzinfo == UTC
