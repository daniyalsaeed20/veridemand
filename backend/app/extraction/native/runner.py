"""Subprocess runner for native extraction workers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import shutil
import sys
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


@dataclass(frozen=True, slots=True)
class NativeWorkerOutcome:
    summary: NativeDocumentSummary
    pages: list[NativePageResult]
    exit_code: int


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

        command = [
            self._python,
            "-m",
            "backend.app.extraction.native.worker",
            "--request",
            str(request_path),
            "--output",
            str(output_path),
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._env(),
            cwd=self._repo_root,
        )

        stdout_task = asyncio.create_task(
            self._read_stdout(process, on_progress), name="native-worker-stdout"
        )
        cancel_watcher: asyncio.Task[None] | None = None
        if cancel_token is not None:
            cancel_watcher = asyncio.create_task(
                self._watch_cancel(cancel_token, process), name="native-worker-cancel"
            )

        try:
            try:
                await asyncio.wait_for(process.wait(), timeout=self._timeout)
            except TimeoutError as exc:
                await self._terminate(process)
                raise NativeExtractionError(
                    ErrorCode.NATIVE_EXTRACTION_TIMEOUT,
                    "Native extraction timed out.",
                ) from exc

            if cancel_token is not None and cancel_token.cancelled:
                await self._terminate(process)
                raise JobCancelledError()

            exit_code = process.returncode if process.returncode is not None else 1
            await stdout_task

            if exit_code != 0:
                raise NativeExtractionError(
                    ErrorCode.NATIVE_WORKER_FAILED,
                    "Native extraction worker failed.",
                )
            if not output_path.is_file():
                raise NativeExtractionError(
                    ErrorCode.NATIVE_WORKER_OUTPUT_INVALID,
                    "Native extraction worker produced no output.",
                )
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                summary = NativeDocumentSummary.model_validate(payload["summary"])
                pages = [NativePageResult.model_validate(p) for p in payload["pages"]]
            except Exception as exc:
                raise NativeExtractionError(
                    ErrorCode.NATIVE_WORKER_OUTPUT_INVALID,
                    "Native extraction worker output was invalid.",
                ) from exc

            for page in pages:
                if page.decision.value != "accepted" and (
                    page.words or page.characters or page.provisional_native_text
                ):
                    raise NativeExtractionError(
                        ErrorCode.NATIVE_WORKER_OUTPUT_INVALID,
                        "Rejected native page output contained text.",
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
            process = await asyncio.create_subprocess_exec(
                self._python,
                "-m",
                "backend.app.extraction.native.worker",
                "--request",
                str(request_path),
                "--output",
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env(),
                cwd=self._repo_root,
            )
            await asyncio.wait_for(process.wait(), timeout=30)
            return process.returncode == 0 and output_path.is_file()
        except Exception:
            return False
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    async def _watch_cancel(
        self, token: CancellationToken, process: asyncio.subprocess.Process
    ) -> None:
        while process.returncode is None:
            if token.cancelled:
                await self._terminate(process)
                return
            await asyncio.sleep(0.05)

    async def _read_stdout(
        self,
        process: asyncio.subprocess.Process,
        on_progress: ProgressCallback | None,
    ) -> None:
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
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

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self._grace)
        except TimeoutError:
            process.kill()
            await process.wait()
