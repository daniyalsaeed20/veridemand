"""Handshake timeout when the OCR child never becomes ready."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.settings.config import Settings

_HANG_WORKER = r"""
import sys
import time
sys.stderr.write("hanging\n")
sys.stderr.flush()
time.sleep(60)
"""


@pytest.mark.asyncio
async def test_startup_handshake_timeout(tmp_path: Path) -> None:
    settings = Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=True,
        ocr_worker_startup_timeout_seconds=2,
        render_concurrency=1,
        ocr_concurrency=1,
    )
    manager = OcrWorkerManager(settings)

    def _spawn_hang() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, "-c", _HANG_WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )

    manager._spawn = _spawn_hang  # type: ignore[method-assign]
    with pytest.raises(VisualOcrError) as exc_info:
        await asyncio.wait_for(manager.start(), timeout=15)
    assert exc_info.value.code in {
        ErrorCode.OCR_WORKER_START_FAILED,
        ErrorCode.OCR_WORKER_NOT_READY,
    }
    await manager.stop()
