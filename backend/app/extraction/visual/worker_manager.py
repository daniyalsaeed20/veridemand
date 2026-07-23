"""Long-lived OCR worker manager using subprocess.Popen supervision."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import subprocess
import sys
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.model_paths import resolve_ocr_model_root
from backend.app.extraction.visual.models import OcrRuntimeConfig, VisualWorkerRequest
from backend.app.extraction.visual.protocol import encode_message, parse_message
from backend.app.processing.cancellation import CancellationToken, JobCancelledError
from backend.app.settings.config import Settings

logger = logging.getLogger("veridemand.visual.worker_manager")

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
_STDERR_MAX_BYTES = 8_192


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
    pages_since_start: int = 0
    stdout_reader_alive: bool = False
    stderr_reader_alive: bool = False


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

    @property
    def ready(self) -> bool:
        process = self._state.process
        readers_ok = self._state.stdout_reader_alive and self._state.stderr_reader_alive
        return self._state.ready and process is not None and process.poll() is None and readers_ok

    def describe(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "restarts": self._state.restarts,
            "pid": self._state.process.pid if self._state.process else None,
            "stdout_reader_alive": self._state.stdout_reader_alive,
            "stderr_reader_alive": self._state.stderr_reader_alive,
        }

    def last_stderr_snippet(self) -> str:
        """Return a privacy-safe truncated stderr ring (no OCR text expected)."""

        if not self._stderr_chunks:
            return ""
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")[-500:]

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
        async with self._lock:
            if self.ready:
                return
            await self._start_locked()

    async def _start_locked(self) -> None:
        self._state.ready = False
        self._stderr_chunks = []
        self._stderr_size = 0
        self._reader_flags = _ReaderFlags()
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
        # Brief yield so reader threads mark themselves alive.
        await asyncio.sleep(0)
        self._sync_reader_flags()

        logger.info(
            "OCR worker process started",
            extra={
                "component": "OcrWorkerManager",
                "operation": "spawn_worker",
                "pid": process.pid,
            },
        )

        deadline = loop.time() + self._settings.ocr_worker_startup_timeout_seconds
        while loop.time() < deadline:
            self._sync_reader_flags()
            if process.poll() is not None:
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_START_FAILED,
                    "OCR worker exited during startup.",
                    operation="await_ready",
                    failing_component="OcrWorkerManager",
                    worker_exit_code=process.returncode,
                )
            try:
                line = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                continue
            if line is None:
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_START_FAILED,
                    "OCR worker stdout closed during startup.",
                    operation="await_ready",
                    failing_component="OcrWorkerManager",
                )
            try:
                message = parse_message(line)
            except Exception:
                logger.warning(
                    "Ignoring malformed OCR worker NDJSON during startup",
                    extra={"component": "OcrWorkerManager", "operation": "await_ready"},
                )
                continue
            if message and message.get("type") == "worker.starting":
                logger.info(
                    "OCR worker loading models",
                    extra={
                        "component": "OcrWorkerManager",
                        "operation": "model_load",
                        "pid": process.pid,
                    },
                )
                continue
            if message and message.get("type") == "worker.ready":
                self._state.ready = True
                self._sync_reader_flags()
                logger.info(
                    "OCR worker ready",
                    extra={
                        "component": "OcrWorkerManager",
                        "operation": "worker_ready",
                        "pid": process.pid,
                    },
                )
                return
            if message and message.get("type") == "worker.failed":
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_START_FAILED,
                    "OCR worker reported startup failure.",
                    operation="await_ready",
                    failing_component="OcrWorkerManager",
                )
        await self._terminate_locked()
        raise VisualOcrError(
            ErrorCode.OCR_WORKER_START_FAILED,
            "OCR worker startup timed out.",
            operation="await_ready",
            failing_component="OcrWorkerManager",
        )

    async def stop(self) -> None:
        async with self._lock:
            await self._terminate_locked()

    async def _terminate_locked(self) -> None:
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

    async def restart(self) -> None:
        async with self._lock:
            if self._state.restarts >= self._settings.ocr_max_worker_restarts:
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_RESTART_LIMIT,
                    "OCR worker restart limit reached.",
                    operation="restart",
                    failing_component="OcrWorkerManager",
                )
            await self._terminate_locked()
            self._state.restarts += 1
            await self._start_locked()

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
        )

    async def process_document(
        self,
        request: VisualWorkerRequest,
        *,
        cancel_token: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> list[dict[str, Any]]:
        """Submit one document job and collect privacy-safe progress events."""

        async with self._lock:
            if not self.ready:
                await self._start_locked()
            process = self._state.process
            queue = self._stdout_queue
            if process is None or process.stdin is None or queue is None:
                raise VisualOcrError(
                    ErrorCode.OCR_WORKER_NOT_READY,
                    "OCR worker is not ready.",
                    operation="process_document",
                    failing_component="OcrWorkerManager",
                )

            await self._write_stdin(
                process,
                encode_message({"type": "process_document", "request": request.to_dict()}),
            )

            events: list[dict[str, Any]] = []
            timeout = self._settings.ocr_document_timeout_seconds
            page_timeout = self._settings.ocr_page_timeout_seconds
            deadline = asyncio.get_running_loop().time() + timeout
            page_deadline = asyncio.get_running_loop().time() + page_timeout
            last_heartbeat = asyncio.get_running_loop().time()
            while True:
                self._sync_reader_flags()
                if not self._state.stdout_reader_alive and process.poll() is None:
                    raise VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker stdout reader died.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                if cancel_token is not None and cancel_token.cancelled:
                    with contextlib.suppress(VisualOcrError):
                        await self._write_stdin(
                            process,
                            encode_message({"type": "cancel", "request_id": request.request_id}),
                        )
                    await self._terminate_locked()
                    with contextlib.suppress(VisualOcrError):
                        await self._start_locked()
                    raise JobCancelledError()
                if process.poll() is not None:
                    self._state.ready = False
                    raise VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker crashed during document processing.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                        worker_exit_code=process.returncode,
                    )
                now = asyncio.get_running_loop().time()
                remaining = deadline - now
                if remaining <= 0:
                    await self._terminate_locked()
                    with contextlib.suppress(VisualOcrError):
                        await self._start_locked()
                    raise VisualOcrError(
                        ErrorCode.OCR_DOCUMENT_TIMEOUT,
                        "Visual OCR document processing timed out.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                if now > page_deadline:
                    await self._terminate_locked()
                    with contextlib.suppress(VisualOcrError):
                        await self._start_locked()
                    raise VisualOcrError(
                        ErrorCode.OCR_PAGE_TIMEOUT,
                        "Visual OCR page processing timed out.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                if now - last_heartbeat >= 5.0:
                    last_heartbeat = now
                    if on_progress is not None:
                        heartbeat = {
                            "type": "worker.heartbeat",
                            "request_id": request.request_id,
                            "elapsed_seconds": round(timeout - remaining, 1),
                            "pid": process.pid,
                        }
                        result = on_progress(heartbeat)
                        if asyncio.iscoroutine(result):
                            await result
                try:
                    line = await asyncio.wait_for(
                        queue.get(), timeout=min(1.0, remaining, page_deadline - now)
                    )
                except TimeoutError:
                    continue
                if line is None:
                    self._state.ready = False
                    raise VisualOcrError(
                        ErrorCode.OCR_WORKER_CRASHED,
                        "OCR worker stdout closed unexpectedly.",
                        operation="process_document",
                        failing_component="OcrWorkerManager",
                    )
                try:
                    message = parse_message(line)
                except Exception:
                    logger.warning(
                        "Ignoring malformed OCR worker NDJSON",
                        extra={"component": "OcrWorkerManager", "operation": "process_document"},
                    )
                    continue
                if message is None:
                    continue
                events.append(message)
                msg_type = message.get("type")
                if msg_type in {
                    "page.started",
                    "page.rendered",
                    "page.ocr_started",
                    "page.completed",
                    "page.failed",
                }:
                    page_deadline = asyncio.get_running_loop().time() + page_timeout
                if on_progress is not None:
                    result = on_progress(message)
                    if asyncio.iscoroutine(result):
                        await result
                if msg_type in {"document.completed", "document.failed", "document.cancelled"}:
                    if msg_type == "document.cancelled":
                        raise JobCancelledError()
                    return events
                if msg_type in {"worker.recycle_recommended", "worker.recycle_requested"}:
                    continue
                if msg_type == "error":
                    code_token = str(message.get("code") or ErrorCode.OCR_WORKER_CRASHED.value)
                    try:
                        code = ErrorCode(code_token)
                    except ValueError:
                        code = ErrorCode.OCR_WORKER_CRASHED
                    raise VisualOcrError(
                        code,
                        "OCR worker reported an error.",
                        operation=str(message.get("operation") or "process_document"),
                        failing_component="OcrWorkerManager",
                    )


# Public alias matching package exports.
VisualOcrWorkerManager = OcrWorkerManager
