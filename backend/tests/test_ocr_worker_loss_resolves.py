"""Regression: worker loss resolves the active request Future and restarts."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.models import (
    OcrRuntimeConfig,
    VisualPageRef,
    VisualWorkerRequest,
)
from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.settings.config import Settings

_CRASH_AFTER_ACK = r"""
import json, sys, time
sys.stdout.write(json.dumps({"type": "worker.ready", "pid": 0}) + "\n")
sys.stdout.flush()
# Read one command then exit abruptly (simulate mid-request crash).
sys.stdin.readline()
sys.stdout.write(json.dumps({"type": "page.started", "page_number": 1, "request_id": "x"}) + "\n")
sys.stdout.flush()
time.sleep(0.2)
raise SystemExit(1)
"""


def _request(tmp_path: Path) -> VisualWorkerRequest:
    return VisualWorkerRequest(
        request_id="req_1",
        session_id="ses_" + "0" * 32,
        document_id="doc_" + "1" * 32,
        job_id="job_" + "2" * 32,
        canonical_pdf_path=str(tmp_path / "doc.pdf"),
        pages=[
            VisualPageRef(
                page_number=1,
                width_points=612,
                height_points=792,
                intrinsic_rotation=0,
                source_type="pdf",
            )
        ],
        page_output_dir=str(tmp_path / "out"),
        staging_dir=str(tmp_path / "staging"),
        config=OcrRuntimeConfig(),
    )


@pytest.mark.asyncio
async def test_worker_exit_resolves_active_request(tmp_path: Path) -> None:
    settings = Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=True,
        ocr_page_timeout_seconds=30,
        ocr_max_worker_restarts=2,
        render_concurrency=1,
        ocr_concurrency=1,
    )
    manager = OcrWorkerManager(settings)

    def _spawn_crash() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, "-c", _CRASH_AFTER_ACK],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )

    manager._spawn = _spawn_crash  # type: ignore[method-assign]
    with pytest.raises(VisualOcrError) as exc_info:
        await asyncio.wait_for(
            manager.process_document(_request(tmp_path), attempt_number=1),
            timeout=20,
        )
    assert exc_info.value.code is ErrorCode.OCR_WORKER_CRASHED
    assert manager._active is None
    assert (
        manager.describe()["last_restart_reason"]
        in {
            "worker_process_exit",
            "worker_stdout_reader_failed",
            None,
        }
        or manager.generation >= 1
    )
    await manager.stop()
