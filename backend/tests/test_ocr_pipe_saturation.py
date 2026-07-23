"""Regression: OCR parent keeps draining when the child floods stderr."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.settings.config import Settings

_FAKE_WORKER = r"""
import json
import sys
import time

# Flood stderr beyond a typical Windows pipe buffer while staying alive.
blob = (b"x" * 4096) + b"\n"
for _ in range(64):
    sys.stderr.buffer.write(blob)
    sys.stderr.buffer.flush()
sys.stdout.write(json.dumps({"type": "worker.ready", "pid": 0}) + "\n")
sys.stdout.flush()
# Stay alive until parent terminates us.
time.sleep(30)
"""


@pytest.mark.asyncio
async def test_stderr_flood_does_not_block_ready_handshake(tmp_path: Path) -> None:
    settings = Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=True,
        ocr_worker_startup_timeout_seconds=15,
        render_concurrency=1,
        ocr_concurrency=1,
    )
    manager = OcrWorkerManager(settings)

    def _spawn_fake() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [sys.executable, "-c", _FAKE_WORKER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )

    manager._spawn = _spawn_fake  # type: ignore[method-assign]
    try:
        await asyncio.wait_for(manager.start(), timeout=20)
        assert manager.ready is True
        assert manager.describe()["stderr_reader_alive"] is True
        snippet = manager.last_stderr_snippet()
        assert len(snippet) > 0
        assert len(snippet.encode("utf-8", errors="replace")) <= 8192
    finally:
        await manager.stop()
        assert manager.ready is False
