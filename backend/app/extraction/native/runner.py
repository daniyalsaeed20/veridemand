"""Subprocess runner for native extraction workers.

Uses ``subprocess.Popen`` with async supervision so the worker starts on every
supported event loop, including Windows ``SelectorEventLoop`` used by uvicorn
``--reload`` / multi-worker. Isolation is unchanged: pdfplumber runs only in the
child ``python -m backend.app.extraction.native.worker`` process.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.native import NativeDocumentSummary, NativePageResult
from backend.app.extraction.native.errors import NativeExtractionError
from backend.app.extraction.native.models import NativeTrustPolicyConfig, NativeWorkerRequest
from backend.app.processing.cancellation import CancellationToken, JobCancelledError

logger = logging.getLogger("veridemand.native.runner")

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]
_STDERR_MAX_BYTES = 8_192


@dataclass(frozen=True, slots=True)
class NativeWorkerOutcome:
    summary: NativeDocumentSummary
    pages: list[NativePageResult]
    exit_code: int


def _parse_error_envelope(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("status") != "failed":
        return None
    error = payload.get("error")
    if not isinstance(error, dict):
        return None
    return error


def _error_code_from_token(token: str) -> ErrorCode:
    try:
        return ErrorCode(token)
    except ValueError:
        return ErrorCode.NATIVE_WORKER_FAILED


def _popen_kwargs() -> dict[str, Any]:
    """Platform-specific Popen flags for reliable terminate/kill."""

    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        # New process group so terminate/kill can target the worker tree.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    return kwargs


class NativeExtractionRunner:
    """Start, supervise, and harvest a native extraction subprocess."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        timeout_seconds: float = 600.0,
        grace_seconds: float = 5.0,
    ) -> None:
        self._python = python_executable or sys.executable
        self._timeout = timeout_seconds
        self._grace = grace_seconds
        self._repo_root = str(Path(__file__).resolve().parents[4])

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            self._repo_root if not existing else f"{self._repo_root}{os.pathsep}{existing}"
        )
        return env

    def _command(self, request_path: Path, output_path: Path) -> list[str]:
        return [
            self._python,
            "-m",
            "backend.app.extraction.native.worker",
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ]

    def _spawn(self, command: list[str]) -> subprocess.Popen[bytes]:
        try:
            return subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env(),
                cwd=self._repo_root,
                shell=False,
                **_popen_kwargs(),
            )
        except OSError as exc:
            raise NativeExtractionError(
                ErrorCode.NATIVE_WORKER_START_FAILED,
                "Native extraction worker failed to start.",
                operation="spawn_worker",
                failing_component="NativeExtractionRunner",
            ) from exc

    async def run(
        self,
        request: NativeWorkerRequest,
        *,
        staging_dir: Path,
        cancel_token: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> NativeWorkerOutcome:
        staging_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
        request_path = staging_dir / "request.json"
        output_path = staging_dir / "result.json.part"
        request_path.write_text(
            json.dumps(request.to_dict(), separators=(",", ":")), encoding="utf-8"
        )

        if cancel_token is not None:
            cancel_token.raise_if_cancelled()

        command = self._command(request_path, output_path)
        process = self._spawn(command)

        stdout_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        stderr_chunks: list[bytes] = []
        last_progress: dict[str, Any] | None = None
        loop = asyncio.get_running_loop()
        stdout_thread = threading.Thread(
            target=self._drain_stdout_thread,
            args=(process, stdout_queue, loop),
            name="native-worker-stdout",
            daemon=True,
        )
        stderr_state = {"size": 0}

        def _note_stderr(chunk: bytes) -> None:
            if stderr_state["size"] >= _STDERR_MAX_BYTES:
                return
            remain = _STDERR_MAX_BYTES - stderr_state["size"]
            piece = chunk[:remain]
            stderr_chunks.append(piece)
            stderr_state["size"] += len(piece)

        stderr_thread = threading.Thread(
            target=self._drain_stderr_thread,
            args=(process, _note_stderr),
            name="native-worker-stderr",
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        async def _track_progress(payload: dict[str, Any]) -> None:
            nonlocal last_progress
            last_progress = {
                k: payload.get(k)
                for k in (
                    "type",
                    "code",
                    "exception_type",
                    "component",
                    "operation",
                    "page_number",
                    "recoverable_as_visual_authority",
                    "decision",
                )
                if k in payload
            }
            if on_progress is not None:
                result = on_progress(payload)
                if asyncio.iscoroutine(result):
                    await result

        stdout_task = asyncio.create_task(
            self._consume_stdout(stdout_queue, _track_progress),
            name="native-worker-stdout-consume",
        )
        cancel_watcher: asyncio.Task[None] | None = None
        if cancel_token is not None:
            cancel_watcher = asyncio.create_task(
                self._watch_cancel(cancel_token, process), name="native-worker-cancel"
            )

        try:
            try:
                exit_code = await asyncio.wait_for(
                    self._wait_process(process), timeout=self._timeout
                )
            except TimeoutError as exc:
                await self._terminate(process)
                raise NativeExtractionError(
                    ErrorCode.NATIVE_EXTRACTION_TIMEOUT,
                    "Native extraction timed out.",
                    worker_exit_code=process.returncode,
                    operation="wait_worker",
                    failing_component="NativeExtractionRunner",
                ) from exc

            if cancel_token is not None and cancel_token.cancelled:
                await self._terminate(process)
                raise JobCancelledError()

            await stdout_task
            stdout_thread.join(timeout=2.0)
            stderr_thread.join(timeout=2.0)
            stderr_tail = b"".join(stderr_chunks).decode("utf-8", errors="replace")

            if exit_code != 0:
                envelope = None
                if output_path.is_file():
                    with contextlib.suppress(Exception):
                        envelope = _parse_error_envelope(
                            json.loads(output_path.read_text(encoding="utf-8"))
                        )
                if envelope is None and last_progress and last_progress.get("type") == "error":
                    envelope = last_progress
                code = _error_code_from_token(
                    str((envelope or {}).get("code") or ErrorCode.NATIVE_WORKER_FAILED.value)
                )
                raise NativeExtractionError(
                    code,
                    "Native extraction worker failed.",
                    worker_exit_code=exit_code,
                    operation=str((envelope or {}).get("operation") or "worker_exit"),
                    failing_component=str(
                        (envelope or {}).get("component") or "NativeExtractionRunner"
                    ),
                    page_number=(
                        int(envelope["page_number"])
                        if envelope and isinstance(envelope.get("page_number"), int)
                        else None
                    ),
                    exception_type=(
                        str(envelope["exception_type"])
                        if envelope and envelope.get("exception_type")
                        else None
                    ),
                    recoverable_as_visual_authority=bool(
                        (envelope or {}).get("recoverable_as_visual_authority")
                    ),
                    stderr_tail=stderr_tail or None,
                )
            if not output_path.is_file():
                raise NativeExtractionError(
                    ErrorCode.NATIVE_WORKER_OUTPUT_INVALID,
                    "Native extraction worker produced no output.",
                    worker_exit_code=exit_code,
                    operation="read_worker_output",
                    failing_component="NativeExtractionRunner",
                    stderr_tail=stderr_tail or None,
                )
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                if _parse_error_envelope(payload) is not None:
                    raise ValueError("worker wrote failure envelope instead of results")
                summary = NativeDocumentSummary.model_validate(payload["summary"])
                pages = [NativePageResult.model_validate(p) for p in payload["pages"]]
            except Exception as exc:
                raise NativeExtractionError(
                    ErrorCode.NATIVE_WORKER_OUTPUT_INVALID,
                    "Native extraction worker output was invalid.",
                    worker_exit_code=exit_code,
                    operation="validate_worker_output",
                    failing_component="NativeExtractionRunner",
                    stderr_tail=stderr_tail or None,
                ) from exc

            for page in pages:
                if page.decision.value != "accepted" and (
                    page.words or page.characters or page.provisional_native_text
                ):
                    raise NativeExtractionError(
                        ErrorCode.NATIVE_WORKER_OUTPUT_INVALID,
                        "Rejected native page output contained text.",
                        worker_exit_code=exit_code,
                        operation="privacy_guard",
                        failing_component="NativeExtractionRunner",
                    )

            return NativeWorkerOutcome(summary=summary, pages=pages, exit_code=exit_code)
        except JobCancelledError:
            await self._terminate(process)
            raise
        finally:
            if cancel_watcher is not None:
                cancel_watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cancel_watcher
            if not stdout_task.done():
                stdout_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stdout_task
            if process.returncode is None:
                await self._terminate(process)

    async def self_check(self, staging_dir: Path) -> bool:
        request = NativeWorkerRequest(
            session_id="ses_" + ("0" * 32),
            document_id="doc_" + ("0" * 32),
            job_id="job_" + ("0" * 32),
            canonical_pdf_path="",
            canonicalisation_method="original_pdf",
            pages=[],
            policy=NativeTrustPolicyConfig(),
            self_check=True,
        )
        try:
            staging_dir.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
            request_path = staging_dir / "request.json"
            output_path = staging_dir / "result.json.part"
            request_path.write_text(
                json.dumps(request.to_dict(), separators=(",", ":")), encoding="utf-8"
            )
            process = self._spawn(self._command(request_path, output_path))
            exit_code = await asyncio.wait_for(self._wait_process(process), timeout=30)
            # Drain pipes so the child can exit cleanly on Windows.
            if process.stdout is not None:
                await asyncio.to_thread(process.stdout.read)
            if process.stderr is not None:
                await asyncio.to_thread(process.stderr.read)
            return exit_code == 0 and output_path.is_file()
        except Exception:
            return False
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    async def _wait_process(self, process: subprocess.Popen[bytes]) -> int:
        return int(await asyncio.to_thread(process.wait))

    def _drain_stdout_thread(
        self,
        process: subprocess.Popen[bytes],
        queue: asyncio.Queue[bytes | None],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        assert process.stdout is not None
        try:
            while True:
                line = process.stdout.readline()
                if not line:
                    break
                loop.call_soon_threadsafe(queue.put_nowait, line)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    def _drain_stderr_thread(
        self,
        process: subprocess.Popen[bytes],
        on_chunk: Callable[[bytes], None],
    ) -> None:
        assert process.stderr is not None
        while True:
            chunk = process.stderr.read(1024)
            if not chunk:
                break
            on_chunk(chunk)

    async def _consume_stdout(
        self,
        queue: asyncio.Queue[bytes | None],
        on_progress: ProgressCallback | None,
    ) -> None:
        while True:
            line = await queue.get()
            if line is None:
                return
            try:
                payload = json.loads(line.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            payload.pop("text", None)
            payload.pop("words", None)
            payload.pop("characters", None)
            if on_progress is not None:
                result = on_progress(payload)
                if asyncio.iscoroutine(result):
                    await result

    async def _watch_cancel(
        self, token: CancellationToken, process: subprocess.Popen[bytes]
    ) -> None:
        while process.poll() is None:
            if token.cancelled:
                await self._terminate(process)
                return
            await asyncio.sleep(0.05)

    async def _terminate(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        with contextlib.suppress(ProcessLookupError, OSError):
            process.terminate()
        try:
            await asyncio.wait_for(self._wait_process(process), timeout=self._grace)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                process.kill()
            await self._wait_process(process)
        # Best-effort drain to avoid zombie pipe blocks on Windows.
        if process.stdout is not None:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(process.stdout.read)
        if process.stderr is not None:
            with contextlib.suppress(OSError):
                await asyncio.to_thread(process.stderr.read)
