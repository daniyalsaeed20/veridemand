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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.models import OcrRuntimeConfig, VisualWorkerRequest
from backend.app.extraction.visual.protocol import encode_message, parse_message
from backend.app.processing.cancellation import CancellationToken, JobCancelledError
from backend.app.settings.config import Settings

logger = logging.getLogger("veridemand.visual.worker_manager")

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
_STDERR_MAX_BYTES = 8_192


def _popen_kwargs() -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


@dataclass
class WorkerState:
    process: subprocess.Popen[bytes] | None = None
    ready: bool = False
    restarts: int = 0
    pages_since_start: int = 0


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
        self._drain_tasks: list[asyncio.Task[None]] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def ready(self) -> bool:
        process = self._state.process
        return self._state.ready and process is not None and process.poll() is None

    def describe(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "restarts": self._state.restarts,
            "pid": self._state.process.pid if self._state.process else None,
        }

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            self._repo_root if not existing else f"{self._repo_root}{os.pathsep}{existing}"
        )
        env["OCR_MODEL_ROOT"] = str(self._settings.ocr_model_root)
        env["OCR_DEVICE"] = self._settings.ocr_device
        env["RENDER_CONCURRENCY"] = "1"
        env["OCR_CONCURRENCY"] = "1"
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
    ) -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                loop.call_soon_threadsafe(queue.put_nowait, line)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    def _drain_stderr_thread(self, process: subprocess.Popen[bytes]) -> None:
        assert process.stderr is not None
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
            pass

    async def start(self) -> None:
        async with self._lock:
            if self.ready:
                return
            await self._start_locked()

    async def _start_locked(self) -> None:
        self._state.ready = False
        self._stderr_chunks = []
        self._stderr_size = 0
        process = self._spawn()
        self._state.process = process
        loop = asyncio.get_running_loop()
        self._loop = loop
        queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._stdout_queue = queue
        threading.Thread(
            target=self._drain_stdout_thread,
            args=(process, queue, loop),
            name="ocr-worker-stdout",
            daemon=True,
        ).start()
        threading.Thread(
            target=self._drain_stderr_thread,
            args=(process,),
            name="ocr-worker-stderr",
            daemon=True,
        ).start()

        deadline = loop.time() + self._settings.ocr_worker_startup_timeout_seconds
        while loop.time() < deadline:
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
            message = parse_message(line)
            if message and message.get("type") == "worker.ready":
                self._state.ready = True
                logger.info("OCR worker ready", extra={"pid": process.pid})
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
                process.stdin.write(encode_message({"type": "shutdown"}))
                process.stdin.flush()
        except Exception:
            pass
        with contextlib.suppress(Exception):
            await asyncio.to_thread(process.wait, self._settings.ocr_termination_grace_seconds)
        if process.poll() is None:
            process.kill()
            await asyncio.to_thread(process.wait)
        self._state.process = None

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
        return OcrRuntimeConfig(
            ocr_enabled=s.ocr_enabled,
            ocr_device=s.ocr_device,
            ocr_engine=s.ocr_engine,
            ocr_detection_model_name=s.ocr_detection_model_name,
            ocr_recognition_model_name=s.ocr_recognition_model_name,
            ocr_model_root=str(s.ocr_model_root),
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

            process.stdin.write(
                encode_message({"type": "process_document", "request": request.to_dict()})
            )
            process.stdin.flush()

            events: list[dict[str, Any]] = []
            timeout = self._settings.ocr_document_timeout_seconds
            deadline = asyncio.get_running_loop().time() + timeout
            while True:
                if cancel_token is not None and cancel_token.cancelled:
                    with contextlib.suppress(OSError, BrokenPipeError):
                        if process.stdin is not None:
                            process.stdin.write(
                                encode_message({"type": "cancel", "request_id": request.request_id})
                            )
                            process.stdin.flush()
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
                remaining = deadline - asyncio.get_running_loop().time()
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
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=min(1.0, remaining))
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
                message = parse_message(line)
                if message is None:
                    continue
                events.append(message)
                if on_progress is not None:
                    result = on_progress(message)
                    if asyncio.iscoroutine(result):
                        await result
                msg_type = message.get("type")
                if msg_type in {"document.completed", "document.failed", "document.cancelled"}:
                    if msg_type == "document.cancelled":
                        raise JobCancelledError()
                    return events
                if msg_type in {"worker.recycle_recommended", "worker.recycle_requested"}:
                    # Finish collecting this document; recycle after return.
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
