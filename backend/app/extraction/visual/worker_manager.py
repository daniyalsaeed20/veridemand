"""Long-lived OCR worker manager using subprocess.Popen supervision."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.ocr_runtime import (
    OCR_PROGRESS_STAGES,
    OCR_STAGE_LABELS,
    OcrComponentStatus,
    OcrRuntimeErrorCode,
    OcrRuntimeStage,
    OcrRuntimeState,
    OcrRuntimeStatus,
)
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.model_paths import resolve_ocr_model_root
from backend.app.extraction.visual.models import OcrRuntimeConfig, VisualWorkerRequest
from backend.app.extraction.visual.ocr_readiness import (
    classify_exception,
    classify_worker_failure_payload,
    is_retryable,
    operator_hint_for,
    sanitize_technical_detail,
    user_message_for,
)
from backend.app.extraction.visual.protocol import encode_message, parse_message
from backend.app.observability.stage_log import log_progress
from backend.app.processing.cancellation import CancellationToken, JobCancelledError
from backend.app.settings.config import Settings

logger = logging.getLogger("veridemand.visual.worker_manager")

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
_STDERR_MAX_BYTES = 8_192


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _popen_kwargs() -> dict[str, Any]:
    """Windows: stay in the parent console job so reload kills orphans.

    Do not use CREATE_NEW_PROCESS_GROUP — that detaches the OCR child from the
    uvicorn --reload worker and leaves Paddle processes after file changes.
    """

    return {}


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Force-kill the worker and any grandchildren (Windows-safe)."""

    if process.poll() is not None:
        return
    pid = process.pid
    if sys.platform == "win32":
        with contextlib.suppress(Exception):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                check=False,
                capture_output=True,
                timeout=15,
            )
    with contextlib.suppress(Exception):
        process.kill()
    with contextlib.suppress(Exception):
        process.wait(timeout=10)


@dataclass
class WorkerState:
    process: subprocess.Popen[bytes] | None = None
    ready: bool = False
    restarts: int = 0
    generation: int = 0
    pages_since_start: int = 0
    stdout_reader_alive: bool = False
    stderr_reader_alive: bool = False


@dataclass
class ActiveRequest:
    """Tracks one in-flight document request owned by a worker generation."""

    request_id: str
    owner_generation: int
    document_id: str
    job_id: str
    attempt_number: int
    created_at: float
    page_deadline: float
    document_deadline: float
    future: asyncio.Future[list[dict[str, Any]]]
    state: str = "queued"
    page_number: int | None = None
    page_started_at: float | None = None
    operation: str = "visual_worker_wait"
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _ReaderFlags:
    stdout_alive: bool = False
    stderr_alive: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


class OcrWorkerManager:
    """Owns one long-lived OCR worker subprocess for the application lifespan."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._state = WorkerState()
        self._lock = asyncio.Lock()
        self._repo_root = str(Path(__file__).resolve().parents[4])
        self._python = sys.executable
        self._stdout_queue: asyncio.Queue[bytes | None] | None = None
        self._stderr_chunks: list[bytes] = []
        self._stderr_size = 0
        self._reader_flags = _ReaderFlags()
        self._stdin_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr-stdin")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._active: ActiveRequest | None = None
        self._last_restart_reason: str | None = None
        self._init_running = False
        self._attempt_id: str | None = None
        self._attempt_number = 0
        self._attempt_started_at: datetime | None = None
        self._last_transition_at: datetime | None = None
        self._runtime_state = (
            OcrRuntimeState.DISABLED if not settings.ocr_enabled else OcrRuntimeState.NOT_STARTED
        )
        self._runtime_stage: OcrRuntimeStage | None = None
        self._error_code: OcrRuntimeErrorCode | None = (
            OcrRuntimeErrorCode.OCR_DISABLED if not settings.ocr_enabled else None
        )
        self._user_message: str | None = (
            user_message_for(OcrRuntimeErrorCode.OCR_DISABLED) if not settings.ocr_enabled else None
        )
        self._operator_hint: str | None = None
        if not settings.ocr_enabled:
            self._operator_hint = operator_hint_for(OcrRuntimeErrorCode.OCR_DISABLED)
        self._technical_detail: str | None = None
        self._detector_status = OcrComponentStatus.NOT_APPLICABLE
        self._recognizer_status = OcrComponentStatus.NOT_APPLICABLE
        self._model_verification_status = OcrComponentStatus.NOT_APPLICABLE
        self._test_fail_once_consumed = False
        self._retry_task: asyncio.Task[None] | None = None
        if settings.ocr_enabled:
            self._detector_status = OcrComponentStatus.PENDING
            self._recognizer_status = OcrComponentStatus.PENDING
            self._model_verification_status = OcrComponentStatus.PENDING

    @property
    def ready(self) -> bool:
        process = self._state.process
        readers_ok = self._state.stdout_reader_alive and self._state.stderr_reader_alive
        return self._state.ready and process is not None and process.poll() is None and readers_ok

    @property
    def generation(self) -> int:
        return self._state.generation

    @property
    def initialization_running(self) -> bool:
        return self._init_running

    def describe(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "restarts": self._state.restarts,
            "generation": self._state.generation,
            "pid": self._state.process.pid if self._state.process else None,
            "stdout_reader_alive": self._state.stdout_reader_alive,
            "stderr_reader_alive": self._state.stderr_reader_alive,
            "active_request_id": self._active.request_id if self._active else None,
            "last_restart_reason": self._last_restart_reason,
            "attempt_id": self._attempt_id,
            "attempt_number": self._attempt_number,
            "runtime_state": self._runtime_state.value,
        }

    def last_stderr_snippet(self) -> str:
        """Return a privacy-safe truncated stderr ring (no OCR text expected)."""

        if not self._stderr_chunks:
            return ""
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")[-500:]

    def runtime_status(self) -> OcrRuntimeStatus:
        """Return the structured OCR readiness snapshot (observational)."""

        if not self._settings.ocr_enabled:
            return OcrRuntimeStatus(
                state=OcrRuntimeState.DISABLED,
                stage=None,
                stage_index=None,
                stage_label=None,
                attempt_id=self._attempt_id,
                attempt_number=self._attempt_number,
                attempt_started_at=self._attempt_started_at,
                last_transition_at=self._last_transition_at,
                ready=False,
                retryable=False,
                error_code=OcrRuntimeErrorCode.OCR_DISABLED,
                user_message=user_message_for(OcrRuntimeErrorCode.OCR_DISABLED),
                operator_hint=operator_hint_for(OcrRuntimeErrorCode.OCR_DISABLED),
                technical_detail=None,
                retry_after_seconds=None,
                detector_status=OcrComponentStatus.NOT_APPLICABLE,
                recognizer_status=OcrComponentStatus.NOT_APPLICABLE,
                model_verification_status=OcrComponentStatus.NOT_APPLICABLE,
            )

        stage = self._runtime_stage
        stage_index = None
        stage_label = None
        if stage is not None:
            try:
                stage_index = OCR_PROGRESS_STAGES.index(stage) + 1
            except ValueError:
                stage_index = None
            stage_label = OCR_STAGE_LABELS.get(stage)

        ready = self.ready
        state = self._runtime_state
        if ready:
            state = OcrRuntimeState.READY

        retryable = False
        if state is OcrRuntimeState.FAILED and self._error_code is not None:
            retryable = is_retryable(self._error_code)
        elif state is OcrRuntimeState.NOT_STARTED:
            retryable = True
        elif state in {
            OcrRuntimeState.STARTING,
            OcrRuntimeState.LOADING_DETECTOR,
            OcrRuntimeState.LOADING_RECOGNIZER,
            OcrRuntimeState.WARMING_UP,
        }:
            retryable = False

        retry_after: int | None = None
        if (state is OcrRuntimeState.FAILED and retryable) or state is OcrRuntimeState.NOT_STARTED:
            retry_after = 5
        elif state not in {OcrRuntimeState.READY, OcrRuntimeState.DISABLED, OcrRuntimeState.FAILED}:
            retry_after = 1

        user_message = self._user_message
        if user_message is None:
            if state is OcrRuntimeState.NOT_STARTED:
                user_message = "Printed OCR has not started yet."
            elif state is OcrRuntimeState.READY:
                user_message = "Printed OCR is ready"
            elif state in {
                OcrRuntimeState.STARTING,
                OcrRuntimeState.LOADING_DETECTOR,
                OcrRuntimeState.LOADING_RECOGNIZER,
                OcrRuntimeState.WARMING_UP,
            }:
                user_message = "Printed OCR is starting"

        return OcrRuntimeStatus(
            state=state,
            stage=stage if state is not OcrRuntimeState.READY else None,
            stage_index=stage_index if state is not OcrRuntimeState.READY else None,
            stage_label=stage_label if state is not OcrRuntimeState.READY else None,
            attempt_id=self._attempt_id,
            attempt_number=self._attempt_number,
            attempt_started_at=self._attempt_started_at,
            last_transition_at=self._last_transition_at,
            ready=ready,
            retryable=retryable,
            error_code=self._error_code if state is OcrRuntimeState.FAILED else None,
            user_message=user_message,
            operator_hint=self._operator_hint if state is OcrRuntimeState.FAILED else None,
            technical_detail=self._technical_detail if state is OcrRuntimeState.FAILED else None,
            retry_after_seconds=retry_after,
            detector_status=self._detector_status,
            recognizer_status=self._recognizer_status,
            model_verification_status=self._model_verification_status,
        )

    def _transition(
        self,
        *,
        state: OcrRuntimeState | None = None,
        stage: OcrRuntimeStage | None = None,
        clear_error: bool = False,
        error_code: OcrRuntimeErrorCode | None = None,
        user_message: str | None = None,
        operator_hint: str | None = None,
        technical_detail: str | None = None,
    ) -> None:
        now = _utcnow()
        self._last_transition_at = now
        if state is not None:
            self._runtime_state = state
        if stage is not None:
            self._runtime_stage = stage
            if stage is OcrRuntimeStage.VERIFYING_MODELS:
                self._model_verification_status = OcrComponentStatus.IN_PROGRESS
            elif stage is OcrRuntimeStage.LOADING_DETECTOR:
                self._model_verification_status = OcrComponentStatus.READY
                self._detector_status = OcrComponentStatus.IN_PROGRESS
            elif stage is OcrRuntimeStage.LOADING_RECOGNIZER:
                self._detector_status = OcrComponentStatus.READY
                self._recognizer_status = OcrComponentStatus.IN_PROGRESS
            elif stage is OcrRuntimeStage.WARMING_UP:
                self._recognizer_status = OcrComponentStatus.READY
        if clear_error:
            self._error_code = None
            self._user_message = user_message
            self._operator_hint = None
            self._technical_detail = None
        if error_code is not None:
            self._error_code = error_code
            self._user_message = user_message or user_message_for(error_code)
            self._operator_hint = operator_hint or operator_hint_for(error_code)
            self._technical_detail = sanitize_technical_detail(technical_detail)
        elif user_message is not None:
            self._user_message = user_message

    def _begin_attempt(self) -> None:
        self._attempt_number += 1
        self._attempt_id = str(uuid.uuid4())
        self._attempt_started_at = _utcnow()
        self._state.ready = False
        self._detector_status = OcrComponentStatus.PENDING
        self._recognizer_status = OcrComponentStatus.PENDING
        self._model_verification_status = OcrComponentStatus.PENDING
        self._transition(
            state=OcrRuntimeState.STARTING,
            stage=OcrRuntimeStage.CHECKING_CONFIGURATION,
            clear_error=True,
            user_message="Printed OCR is starting",
        )

    def _mark_ready(self) -> None:
        self._state.ready = True
        self._detector_status = OcrComponentStatus.READY
        self._recognizer_status = OcrComponentStatus.READY
        self._model_verification_status = OcrComponentStatus.READY
        self._runtime_stage = None
        self._transition(
            state=OcrRuntimeState.READY,
            clear_error=True,
            user_message="Printed OCR is ready",
        )

    def _mark_failed(
        self,
        code: OcrRuntimeErrorCode,
        *,
        technical_detail: str | None = None,
        user_message: str | None = None,
        operator_hint: str | None = None,
    ) -> None:
        self._state.ready = False
        if code in {
            OcrRuntimeErrorCode.OCR_DETECTOR_LOAD_FAILED,
            OcrRuntimeErrorCode.OCR_DLL_LOAD_FAILED,
            OcrRuntimeErrorCode.OCR_OUT_OF_MEMORY,
        }:
            self._detector_status = OcrComponentStatus.FAILED
        if code in {
            OcrRuntimeErrorCode.OCR_RECOGNIZER_LOAD_FAILED,
            OcrRuntimeErrorCode.OCR_WARMUP_FAILED,
        }:
            self._recognizer_status = OcrComponentStatus.FAILED
        if code in {
            OcrRuntimeErrorCode.OCR_MODELS_MISSING,
            OcrRuntimeErrorCode.OCR_MODEL_INTEGRITY_FAILED,
        }:
            self._model_verification_status = OcrComponentStatus.FAILED
        self._transition(
            state=OcrRuntimeState.FAILED,
            error_code=code,
            user_message=user_message,
            operator_hint=operator_hint,
            technical_detail=technical_detail,
        )

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            self._repo_root if not existing else f"{self._repo_root}{os.pathsep}{existing}"
        )
        model_root = resolve_ocr_model_root(self._settings.ocr_model_root)
        env["OCR_MODEL_ROOT"] = str(model_root)
        env["OCR_DEVICE"] = self._settings.ocr_device
        env["OCR_CPU_THREADS"] = str(self._settings.ocr_cpu_threads)
        env["RENDER_CONCURRENCY"] = "1"
        env["OCR_CONCURRENCY"] = "1"
        env["FLAGS_use_mkldnn"] = "0"
        env["FLAGS_onednn"] = "0"
        env["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
        env["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        delay = float(self._settings.ocr_test_startup_delay_seconds or 0.0)
        if delay > 0:
            env["OCR_TEST_STARTUP_DELAY_SECONDS"] = str(delay)
        fail_once = (self._settings.ocr_test_fail_once_code or "").strip()
        fail_always = (self._settings.ocr_test_fail_code or "").strip()
        if fail_once and not self._test_fail_once_consumed:
            env["OCR_TEST_FAIL_ONCE_CODE"] = fail_once
            self._test_fail_once_consumed = True
        elif fail_always:
            env["OCR_TEST_FAIL_CODE"] = fail_always
        else:
            env.pop("OCR_TEST_FAIL_ONCE_CODE", None)
            env.pop("OCR_TEST_FAIL_CODE", None)
        return env

    def _spawn(self) -> subprocess.Popen[bytes]:
        command = [self._python, "-m", "backend.app.extraction.visual.worker"]
        try:
            return subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env(),
                cwd=self._repo_root,
                shell=False,
                **_popen_kwargs(),
            )
        except OSError as exc:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_START_FAILED,
                "OCR worker failed to start.",
                operation="spawn_worker",
                failing_component="OcrWorkerManager",
                exception_type=type(exc).__name__,
            ) from exc

    def _drain_stdout_thread(
        self,
        process: subprocess.Popen[bytes],
        queue: asyncio.Queue[bytes | None],
        loop: asyncio.AbstractEventLoop,
        flags: _ReaderFlags,
    ) -> None:
        assert process.stdout is not None
        with flags.lock:
            flags.stdout_alive = True
        try:
            for line in process.stdout:
                try:
                    loop.call_soon_threadsafe(queue.put_nowait, line)
                except RuntimeError:
                    break
        except Exception:
            logger.exception(
                "OCR worker stdout reader failed",
                extra={"component": "OcrWorkerManager", "operation": "drain_stdout"},
            )
        finally:
            with flags.lock:
                flags.stdout_alive = False
            with contextlib.suppress(RuntimeError):
                loop.call_soon_threadsafe(queue.put_nowait, None)

    def _drain_stderr_thread(self, process: subprocess.Popen[bytes], flags: _ReaderFlags) -> None:
        assert process.stderr is not None
        with flags.lock:
            flags.stderr_alive = True
        try:
            while True:
                chunk = process.stderr.read(1024)
                if not chunk:
                    break
                if self._stderr_size >= _STDERR_MAX_BYTES:
                    continue
                remain = _STDERR_MAX_BYTES - self._stderr_size
                piece = chunk[:remain]
                self._stderr_chunks.append(piece)
                self._stderr_size += len(piece)
        except Exception:
            logger.exception(
                "OCR worker stderr reader failed",
                extra={"component": "OcrWorkerManager", "operation": "drain_stderr"},
            )
        finally:
            with flags.lock:
                flags.stderr_alive = False

    def _sync_reader_flags(self) -> None:
        with self._reader_flags.lock:
            self._state.stdout_reader_alive = self._reader_flags.stdout_alive
            self._state.stderr_reader_alive = self._reader_flags.stderr_alive

    async def _write_stdin(self, process: subprocess.Popen[bytes], payload: bytes) -> None:
        if process.stdin is None:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_NOT_READY,
                "OCR worker stdin is closed.",
                operation="write_stdin",
                failing_component="OcrWorkerManager",
            )

        def _write() -> None:
            assert process.stdin is not None
            process.stdin.write(payload)
            process.stdin.flush()

        try:
            await asyncio.get_running_loop().run_in_executor(self._stdin_executor, _write)
        except Exception as exc:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_CRASHED,
                "Failed to write to OCR worker stdin.",
                operation="write_stdin",
                failing_component="OcrWorkerManager",
                exception_type=type(exc).__name__,
            ) from exc

    async def start(self) -> None:
        await self.ensure_started()

    async def ensure_started(self) -> OcrRuntimeStatus:
        """Shared initialization entry used by lifespan and the retry endpoint."""

        if not self._settings.ocr_enabled:
            return self.runtime_status()
        async with self._lock:
            if self.ready:
                return self.runtime_status()
            if self._init_running:
                return self.runtime_status()
            self._init_running = True
            self._begin_attempt()
        try:
            async with self._lock:
                if self.ready:
                    return self.runtime_status()
                await self._start_locked()
        except VisualOcrError as exc:
            code, detail = classify_exception(
                Exception(exc.message),
                operation=exc.operation,
                legacy_code=exc.code,
            )
            if exc.operation == "await_ready" and "timed out" in exc.message.lower():
                code = OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT
            # Prefer failure already recorded from worker.failed.
            if self._runtime_state is not OcrRuntimeState.FAILED:
                self._mark_failed(code, technical_detail=detail or exc.exception_type)
            raise
        except Exception as exc:
            code, detail = classify_exception(exc, operation="ensure_started")
            if self._runtime_state is not OcrRuntimeState.FAILED:
                self._mark_failed(code, technical_detail=detail)
            raise
        finally:
            self._init_running = False
        return self.runtime_status()

    async def retry_initialization(self) -> OcrRuntimeStatus:
        """Accept an operator OCR retry and continue initialization in the background.

        Does not restart the backend operating-system process or FastAPI lifespan.
        """

        if not self._settings.ocr_enabled:
            self._mark_failed(OcrRuntimeErrorCode.OCR_DISABLED)
            return self.runtime_status()

        status = self.runtime_status()
        if self.ready:
            return status
        if self._init_running or status.state in {
            OcrRuntimeState.STARTING,
            OcrRuntimeState.LOADING_DETECTOR,
            OcrRuntimeState.LOADING_RECOGNIZER,
            OcrRuntimeState.WARMING_UP,
        }:
            return status
        if status.state is OcrRuntimeState.FAILED and not status.retryable:
            return status

        async def _run() -> None:
            async with self._lock:
                if self.ready or self._init_running:
                    return
                self._init_running = True
                if self._state.process is not None:
                    await self._terminate_locked(reason="operator_ocr_retry")
                self._begin_attempt()
            try:
                async with self._lock:
                    await self._start_locked()
            except Exception:
                logger.exception(
                    "OCR operator retry failed",
                    extra={"component": "OcrWorkerManager", "operation": "retry_initialization"},
                )
                if self._runtime_state is not OcrRuntimeState.FAILED:
                    self._mark_failed(
                        OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE,
                        technical_detail="operator_retry_failed",
                    )
            finally:
                self._init_running = False

        self._retry_task = asyncio.create_task(_run(), name="ocr-operator-retry")
        # Yield so the task can set attempt metadata before the HTTP response.
        await asyncio.sleep(0)
        return self.runtime_status()

    async def _start_locked(self) -> None:
        self._state.ready = False
        self._stderr_chunks = []
        self._stderr_size = 0
        self._reader_flags = _ReaderFlags()
        self._state.generation += 1
        generation = self._state.generation
        process = self._spawn()
        self._state.process = process
        loop = asyncio.get_running_loop()
        self._loop = loop
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._stdout_queue = queue
        threading.Thread(
            target=self._drain_stdout_thread,
            args=(process, queue, loop, self._reader_flags),
            name="ocr-worker-stdout",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._drain_stderr_thread,
            args=(process, self._reader_flags),
            name="ocr-worker-stderr",
            daemon=True,
        ).start()
        await asyncio.sleep(0)
        self._sync_reader_flags()

        log_progress(
            "ocr_worker_process_started",
            worker_pid=process.pid,
            worker_generation=generation,
            worker_restart_count=self._state.restarts,
            operation="spawn_worker",
            operation_status="started",
        )

        deadline = loop.time() + self._settings.ocr_worker_startup_timeout_seconds
        while loop.time() < deadline:
            self._sync_reader_flags()
            try:
                line = await asyncio.wait_for(queue.get(), timeout=0.5)
            except TimeoutError:
                line = None
            if line is None and process.poll() is not None:
                # Drain any final NDJSON before treating exit as opaque failure.
                while True:
                    try:
                        line = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        line = None
                        break
                    if line is None:
                        break
                    try:
                        message = parse_message(line)
                    except Exception:
                        continue
                    if message and message.get("type") in {"worker.failed", "error"}:
                        code, detail = classify_worker_failure_payload(message)
                        self._mark_failed(
                            code,
                            technical_detail=detail,
                            user_message=str(message.get("user_message") or "") or None,
                            operator_hint=str(message.get("operator_hint") or "") or None,
                        )
                        raise VisualOcrError(
                            ErrorCode.OCR_WORKER_START_FAILED,
                            "OCR worker reported startup failure.",
                            operation="await_ready",
                            failing_component="OcrWorkerManager",
                            exception_type=str(message.get("exception_type") or code.value),
                            worker_exit_code=process.returncode,
                        )
                if self._runtime_state is not OcrRuntimeState.FAILED:
                    detail = sanitize_technical_detail(f"worker_exit:{process.returncode}")
                    self._mark_failed(
                        OcrRuntimeErrorCode.OCR_UNKNOWN_FAILURE,
                        technical_detail=detail,
                    )
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_START_FAILED,
                    "OCR worker exited during startup.",
                    operation="await_ready",
                    failing_component="OcrWorkerManager",
                    worker_exit_code=process.returncode,
                )
            if line is None:
                continue
            try:
                message = parse_message(line)
            except Exception:
                logger.warning(
                    "Ignoring malformed OCR worker NDJSON during startup",
                    extra={"component": "OcrWorkerManager", "operation": "await_ready"},
                )
                continue
            if not message:
                continue
            msg_type = message.get("type")
            if msg_type == "worker.starting":
                self._transition(
                    state=OcrRuntimeState.STARTING,
                    stage=OcrRuntimeStage.CHECKING_CONFIGURATION,
                    user_message="Printed OCR is starting",
                )
                log_progress(
                    "ocr_worker_loading_models",
                    worker_pid=process.pid,
                    worker_generation=generation,
                    operation="model_load",
                    operation_status="started",
                )
                continue
            if msg_type == "worker.stage":
                stage_raw = str(message.get("stage") or "")
                try:
                    stage = OcrRuntimeStage(stage_raw)
                except ValueError:
                    continue
                state_map = {
                    OcrRuntimeStage.CHECKING_CONFIGURATION: OcrRuntimeState.STARTING,
                    OcrRuntimeStage.VERIFYING_MODELS: OcrRuntimeState.STARTING,
                    OcrRuntimeStage.LOADING_DETECTOR: OcrRuntimeState.LOADING_DETECTOR,
                    OcrRuntimeStage.LOADING_RECOGNIZER: OcrRuntimeState.LOADING_RECOGNIZER,
                    OcrRuntimeStage.WARMING_UP: OcrRuntimeState.WARMING_UP,
                }
                self._transition(
                    state=state_map.get(stage, OcrRuntimeState.STARTING),
                    stage=stage,
                    user_message="Printed OCR is starting",
                )
                continue
            if msg_type == "worker.ready":
                self._mark_ready()
                self._sync_reader_flags()
                log_progress(
                    "ocr_worker_ready",
                    worker_pid=process.pid,
                    worker_generation=generation,
                    worker_restart_count=self._state.restarts,
                    operation="worker_ready",
                    operation_status="completed",
                    reason_code="enable_mkldnn=false",
                )
                return
            if msg_type in {"worker.failed", "error"}:
                code, detail = classify_worker_failure_payload(message)
                self._mark_failed(
                    code,
                    technical_detail=detail,
                    user_message=str(message.get("user_message") or "") or None,
                    operator_hint=str(message.get("operator_hint") or "") or None,
                )
                await self._terminate_locked(reason="worker_startup_failed")
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_START_FAILED,
                    "OCR worker reported startup failure.",
                    operation="await_ready",
                    failing_component="OcrWorkerManager",
                    exception_type=str(message.get("exception_type") or code.value),
                )
        await self._terminate_locked(reason="worker_startup_timeout")
        self._mark_failed(
            OcrRuntimeErrorCode.OCR_STARTUP_TIMEOUT,
            technical_detail="startup_timeout",
        )
        raise VisualOcrError(
            ErrorCode.OCR_WORKER_START_FAILED,
            "OCR worker startup timed out.",
            operation="await_ready",
            failing_component="OcrWorkerManager",
        )

    async def stop(self) -> None:
        async with self._lock:
            await self._fail_active(
                VisualOcrError(
                    ErrorCode.OCR_WORKER_CRASHED,
                    "OCR worker shut down.",
                    operation="stop",
                    failing_component="OcrWorkerManager",
                ),
                action="fail",
                reason="worker_manual_shutdown",
            )
            await self._terminate_locked(reason="worker_manual_shutdown")

    async def _fail_active(
        self,
        error: BaseException,
        *,
        action: str,
        reason: str,
    ) -> None:
        active = self._active
        if active is None:
            return
        old_pid = self._state.process.pid if self._state.process else None
        log_progress(
            "ocr_worker_restart" if action == "retry" else "ocr_worker_request_failed",
            level=logging.WARNING,
            document_id=active.document_id,
            job_id=active.job_id,
            request_id=active.request_id,
            page_number=active.page_number,
            operation=active.operation,
            operation_status="retrying" if action == "retry" else "failed",
            worker_pid=old_pid,
            worker_generation=active.owner_generation,
            worker_restart_count=self._state.restarts,
            attempt_number=active.attempt_number,
            max_attempts=2,
            reason_code=reason,
            restart_reason=reason,
            active_request_action=action,
            previous_pid=old_pid,
            previous_generation=active.owner_generation,
        )
        self._last_restart_reason = reason
        if not active.future.done():
            if isinstance(error, Exception):
                active.future.set_exception(error)
            else:
                active.future.set_exception(
                    VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker lost.",
                        operation="fail_active",
                        failing_component="OcrWorkerManager",
                    )
                )
        # Retrieve the exception so asyncio does not warn "Future exception was never retrieved".
        if active.future.done() and not active.future.cancelled():
            with contextlib.suppress(Exception):
                active.future.exception()
        active.state = "failed"
        self._active = None

    async def _terminate_locked(self, *, reason: str = "worker_manual_shutdown") -> None:
        process = self._state.process
        self._state.ready = False
        if process is None:
            return
        try:
            if process.poll() is None and process.stdin is not None:
                await self._write_stdin(process, encode_message({"type": "shutdown"}))
        except Exception:
            pass
        with contextlib.suppress(Exception):
            await asyncio.to_thread(process.wait, self._settings.ocr_termination_grace_seconds)
        if process.poll() is None:
            await asyncio.to_thread(_kill_process_tree, process)
        self._state.process = None
        self._state.stdout_reader_alive = False
        self._state.stderr_reader_alive = False
        self._last_restart_reason = reason

    async def restart(self, *, reason: str = "worker_healthcheck_failed") -> None:
        async with self._lock:
            await self._restart_locked(reason=reason)

    async def _restart_locked(self, *, reason: str) -> None:
        if self._state.restarts >= self._settings.ocr_max_worker_restarts:
            raise VisualOcrError(
                ErrorCode.OCR_WORKER_RESTART_LIMIT,
                "OCR worker restart limit reached.",
                operation="restart",
                failing_component="OcrWorkerManager",
            )
        previous_pid = self._state.process.pid if self._state.process else None
        previous_gen = self._state.generation
        await self._terminate_locked(reason=reason)
        self._state.restarts += 1
        self._begin_attempt()
        await self._start_locked()
        log_progress(
            "ocr_worker_restart",
            level=logging.WARNING,
            worker_pid=self._state.process.pid if self._state.process else None,
            worker_generation=self._state.generation,
            worker_restart_count=self._state.restarts,
            previous_pid=previous_pid,
            previous_generation=previous_gen,
            new_pid=self._state.process.pid if self._state.process else None,
            new_generation=self._state.generation,
            restart_reason=reason,
            reason_code=reason,
            operation="worker_restart",
            operation_status="completed",
            active_request_action="retry" if self._active else "none",
        )

    def config_from_settings(self) -> OcrRuntimeConfig:
        s = self._settings
        model_root = resolve_ocr_model_root(s.ocr_model_root)
        return OcrRuntimeConfig(
            ocr_enabled=s.ocr_enabled,
            ocr_device=s.ocr_device,
            ocr_engine=s.ocr_engine,
            ocr_detection_model_name=s.ocr_detection_model_name,
            ocr_recognition_model_name=s.ocr_recognition_model_name,
            ocr_model_root=str(model_root),
            ocr_cpu_threads=s.ocr_cpu_threads,
            ocr_recognition_batch_size=s.ocr_recognition_batch_size,
            ocr_render_dpi=s.ocr_render_dpi,
            ocr_visibility_probe_dpi=s.ocr_visibility_probe_dpi,
            ocr_min_effective_dpi=s.ocr_min_effective_dpi,
            ocr_max_render_pixels=s.ocr_max_render_pixels,
            ocr_max_render_side_pixels=s.ocr_max_render_side_pixels,
            ocr_text_det_limit_side_len=s.ocr_text_det_limit_side_len,
            ocr_text_det_limit_type=s.ocr_text_det_limit_type,
            ocr_text_det_thresh=s.ocr_text_det_thresh,
            ocr_text_det_box_thresh=s.ocr_text_det_box_thresh,
            ocr_text_det_unclip_ratio=s.ocr_text_det_unclip_ratio,
            ocr_min_recognition_score=s.ocr_min_recognition_score,
            ocr_low_confidence_score=s.ocr_low_confidence_score,
            ocr_enable_grayscale_fallback=s.ocr_enable_grayscale_fallback,
            ocr_fallback_max_attempts=s.ocr_fallback_max_attempts,
            ocr_page_timeout_seconds=s.ocr_page_timeout_seconds,
            ocr_max_worker_rss_mb=s.ocr_max_worker_rss_mb,
            ocr_worker_recycle_after_pages=s.ocr_worker_recycle_after_pages,
            ocr_save_rendered_pages=s.ocr_save_rendered_pages,
            ocr_keep_failed_render=s.ocr_keep_failed_render,
            ocr_layout_max_vertical_gap_ratio=s.ocr_layout_max_vertical_gap_ratio,
            ocr_layout_min_horizontal_overlap_ratio=s.ocr_layout_min_horizontal_overlap_ratio,
            ocr_column_gap_ratio=s.ocr_column_gap_ratio,
            canonical_page_dimension_tolerance_points=s.canonical_page_dimension_tolerance_points,
            ocr_fast_pass_enabled=s.ocr_fast_pass_enabled,
            ocr_primary_limit_side_len=s.ocr_primary_limit_side_len,
            ocr_fallback_limit_side_len=s.ocr_fallback_limit_side_len,
            ocr_fast_pass_min_detections=s.ocr_fast_pass_min_detections,
            ocr_fast_pass_min_average_confidence=s.ocr_fast_pass_min_average_confidence,
            ocr_fast_pass_min_coverage=s.ocr_fast_pass_min_coverage,
        )

    async def process_document(
        self,
        request: VisualWorkerRequest,
        *,
        cancel_token: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
        attempt_number: int = 1,
    ) -> list[dict[str, Any]]:
        """Submit one document job and collect privacy-safe progress events."""

        async with self._lock:
            if not self.ready:
                await self._start_locked()
            process = self._state.process
            queue = self._stdout_queue
            generation = self._state.generation
            if process is None or process.stdin is None or queue is None:
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_NOT_READY,
                    "OCR worker is not ready.",
                    operation="process_document",
                    failing_component="OcrWorkerManager",
                )

            loop = asyncio.get_running_loop()
            page_timeout = float(self._settings.ocr_page_timeout_seconds)
            doc_timeout = float(self._settings.ocr_document_timeout_seconds)
            now = loop.time()
            future: asyncio.Future[list[dict[str, Any]]] = loop.create_future()
            active = ActiveRequest(
                request_id=request.request_id,
                owner_generation=generation,
                document_id=request.document_id,
                job_id=request.job_id,
                attempt_number=attempt_number,
                created_at=now,
                page_deadline=now + page_timeout,
                document_deadline=now + doc_timeout,
                future=future,
                state="writing",
                operation="visual_worker_wait",
            )
            self._active = active

            try:
                await self._write_stdin(
                    process,
                    encode_message(
                        {
                            "type": "process_document",
                            "request": request.to_dict(),
                            "worker_generation": generation,
                            "attempt_number": attempt_number,
                        }
                    ),
                )
            except VisualOcrError as exc:
                await self._fail_active(exc, action="fail", reason="worker_stdin_write_failed")
                with contextlib.suppress(VisualOcrError):
                    await self._restart_locked(reason="worker_stdin_write_failed")
                raise

            active.state = "submitted"
            last_heartbeat = now
            page_deadline_armed = False

            while True:
                self._sync_reader_flags()
                if not self._state.stdout_reader_alive and process.poll() is None:
                    err = VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker stdout reader died.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                    await self._fail_active(
                        err, action="retry", reason="worker_stdout_reader_failed"
                    )
                    with contextlib.suppress(VisualOcrError):
                        await self._restart_locked(reason="worker_stdout_reader_failed")
                    raise err
                if cancel_token is not None and cancel_token.cancelled:
                    with contextlib.suppress(VisualOcrError):
                        await self._write_stdin(
                            process,
                            encode_message({"type": "cancel", "request_id": request.request_id}),
                        )
                    await self._fail_active(
                        JobCancelledError(),
                        action="fail",
                        reason="worker_manual_shutdown",
                    )
                    await self._terminate_locked(reason="worker_manual_shutdown")
                    with contextlib.suppress(VisualOcrError):
                        await self._restart_locked(reason="worker_manual_shutdown")
                    raise JobCancelledError()
                if process.poll() is not None:
                    self._state.ready = False
                    err = VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker crashed during document processing.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                        worker_exit_code=process.returncode,
                    )
                    await self._fail_active(err, action="retry", reason="worker_process_exit")
                    with contextlib.suppress(VisualOcrError):
                        await self._restart_locked(reason="worker_process_exit")
                    raise err

                now = loop.time()
                remaining_doc = active.document_deadline - now
                remaining_page = active.page_deadline - now
                if remaining_doc <= 0:
                    err = VisualOcrError(
                        ErrorCode.OCR_DOCUMENT_TIMEOUT,
                        "Visual OCR document processing timed out.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                    await self._fail_active(err, action="fail", reason="worker_response_timeout")
                    with contextlib.suppress(VisualOcrError):
                        await self._restart_locked(reason="worker_response_timeout")
                    raise err
                if page_deadline_armed and remaining_page <= 0:
                    err = VisualOcrError(
                        ErrorCode.OCR_PAGE_TIMEOUT,
                        "Visual OCR page processing timed out.",
                        operation=active.operation or "paddle_ocr_pipeline",
                        failing_component="OcrWorkerManager",
                    )
                    # Final attempt: do not spawn an unused worker after failing the request.
                    max_attempts = 2
                    final_attempt = attempt_number >= max_attempts
                    await self._fail_active(
                        err,
                        action="fail" if final_attempt else "retry",
                        reason="worker_page_timeout",
                    )
                    if not final_attempt:
                        with contextlib.suppress(VisualOcrError):
                            await self._restart_locked(reason="worker_page_timeout")
                    raise err

                if now - last_heartbeat >= 5.0:
                    last_heartbeat = now
                    if on_progress is not None:
                        now_hb = loop.time()
                        remaining_doc_hb = active.document_deadline - now_hb
                        remaining_page_hb = active.page_deadline - now_hb
                        remaining = remaining_doc_hb
                        if page_deadline_armed:
                            remaining = min(remaining_doc_hb, remaining_page_hb)
                        page_elapsed = None
                        if active.page_started_at is not None:
                            page_elapsed = round(now_hb - active.page_started_at, 1)
                        heartbeat = {
                            "type": "worker.heartbeat",
                            "request_id": request.request_id,
                            "elapsed_seconds": round(now_hb - active.created_at, 1),
                            "document_elapsed_seconds": round(now_hb - active.created_at, 1),
                            "page_elapsed_seconds": page_elapsed,
                            "deadline_remaining_seconds": round(max(0.0, remaining), 1),
                            "document_deadline_remaining_seconds": round(
                                max(0.0, remaining_doc_hb), 1
                            ),
                            "page_deadline_remaining_seconds": (
                                round(max(0.0, remaining_page_hb), 1)
                                if page_deadline_armed
                                else None
                            ),
                            "pid": process.pid,
                            "worker_generation": generation,
                            "attempt_number": attempt_number,
                            "operation": active.operation,
                            "page_number": active.page_number,
                        }
                        result = on_progress(heartbeat)
                        if asyncio.iscoroutine(result):
                            await result

                wait_for = min(1.0, remaining_doc)
                if page_deadline_armed:
                    wait_for = min(wait_for, max(0.05, remaining_page))
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=wait_for)
                except TimeoutError:
                    continue
                if line is None:
                    self._state.ready = False
                    err = VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker stdout closed unexpectedly.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                    await self._fail_active(err, action="retry", reason="worker_process_exit")
                    with contextlib.suppress(VisualOcrError):
                        await self._restart_locked(reason="worker_process_exit")
                    raise err
                try:
                    message = parse_message(line)
                except Exception:
                    err = VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker sent a malformed protocol message.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                    await self._fail_active(err, action="retry", reason="worker_protocol_error")
                    with contextlib.suppress(VisualOcrError):
                        await self._restart_locked(reason="worker_protocol_error")
                    raise err from None
                if message is None:
                    continue
                msg_gen = message.get("worker_generation")
                if msg_gen is not None and int(msg_gen) != generation:
                    continue  # stale generation — ignore
                message["worker_generation"] = generation
                message["attempt_number"] = attempt_number
                message["worker_restart_count"] = self._state.restarts
                emit_now = loop.time()
                remaining_doc_emit = active.document_deadline - emit_now
                remaining_page_emit = active.page_deadline - emit_now
                remaining_emit = remaining_doc_emit
                if page_deadline_armed:
                    remaining_emit = min(remaining_doc_emit, remaining_page_emit)
                message["deadline_remaining_seconds"] = round(max(0.0, remaining_emit), 1)
                message["document_deadline_remaining_seconds"] = round(
                    max(0.0, remaining_doc_emit), 1
                )
                message["page_deadline_remaining_seconds"] = (
                    round(max(0.0, remaining_page_emit), 1) if page_deadline_armed else None
                )
                message["document_elapsed_seconds"] = round(emit_now - active.created_at, 1)
                if active.page_started_at is not None:
                    message["page_elapsed_seconds"] = round(emit_now - active.page_started_at, 1)
                active.events.append(message)
                msg_type = str(message.get("type") or "")
                if msg_type == "page.started":
                    active.page_number = (
                        int(message["page_number"])
                        if isinstance(message.get("page_number"), (int, float, str))
                        else active.page_number
                    )
                    active.operation = "visual_page_render"
                    active.state = "running"
                    active.page_started_at = emit_now
                    # End-to-end page deadline from page start (not sliding per event).
                    active.page_deadline = emit_now + page_timeout
                    page_deadline_armed = True
                    message["deadline_remaining_seconds"] = round(page_timeout, 1)
                    message["page_elapsed_seconds"] = 0.0
                elif msg_type == "page.rendered":
                    active.operation = "visual_preprocessing"
                elif msg_type in {"page.ocr_started", "page.ocr_completed"}:
                    active.operation = "paddle_ocr_pipeline"
                elif msg_type in {"page.mapping_started", "page.mapping_completed"}:
                    active.operation = "visual_coordinate_mapping"
                elif msg_type in {"page.grouping_started", "page.grouping_completed"}:
                    active.operation = "visual_line_grouping"
                elif msg_type in {"page.completed", "page.failed"}:
                    active.operation = "visual_page_publication"
                    page_deadline_armed = False
                    # Recalculate remaining at completion; do not copy heartbeat value.
                    message["deadline_remaining_seconds"] = round(
                        max(0.0, active.document_deadline - emit_now), 1
                    )
                if on_progress is not None:
                    result = on_progress(message)
                    if asyncio.iscoroutine(result):
                        await result
                if msg_type in {"document.completed", "document.failed", "document.cancelled"}:
                    if msg_type == "document.cancelled":
                        await self._fail_active(
                            JobCancelledError(), action="fail", reason="worker_manual_shutdown"
                        )
                        raise JobCancelledError()
                    events = list(active.events)
                    if not active.future.done():
                        active.future.set_result(events)
                    if active.future.done() and not active.future.cancelled():
                        with contextlib.suppress(Exception):
                            _ = active.future.result()
                    active.state = "completed"
                    self._active = None
                    return events
                if msg_type in {"worker.recycle_recommended", "worker.recycle_requested"}:
                    continue
                if msg_type == "error":
                    code_token = str(message.get("code") or ErrorCode.OCR_WORKER_CRASHED.value)
                    try:
                        code = ErrorCode(code_token)
                    except ValueError:
                        code = ErrorCode.OCR_WORKER_CRASHED
                    err = VisualOcrError(
                        code,
                        "OCR worker reported an error.",
                        operation=str(message.get("operation") or "process_document"),
                        failing_component="OcrWorkerManager",
                    )
                    await self._fail_active(err, action="retry", reason="worker_protocol_error")
                    with contextlib.suppress(VisualOcrError):
                        await self._restart_locked(reason="worker_protocol_error")
                    raise err

        return []  # unreachable; satisfies type checkers when loop exits unexpectedly


# Public alias matching package exports.
VisualOcrWorkerManager = OcrWorkerManager
