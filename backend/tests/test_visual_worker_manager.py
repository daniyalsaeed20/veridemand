"""Unit tests for OCR worker manager lifecycle without spawning Paddle."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.settings.config import Settings


def test_manager_not_ready_before_start(tmp_path: Path) -> None:
    settings = Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=False,
        render_concurrency=1,
        ocr_concurrency=1,
    )
    manager = OcrWorkerManager(settings)
    assert manager.ready is False
    described = manager.describe()
    assert described["ready"] is False
    assert described["pid"] is None


def test_config_from_settings_maps_model_names(tmp_path: Path) -> None:
    settings = Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=True,
        ocr_detection_model_name="PP-OCRv6_medium_det",
        ocr_recognition_model_name="PP-OCRv6_medium_rec",
        ocr_render_dpi=200,
    )
    config = OcrWorkerManager(settings).config_from_settings()
    assert config.ocr_detection_model_name == "PP-OCRv6_medium_det"
    assert config.ocr_recognition_model_name == "PP-OCRv6_medium_rec"
    assert config.ocr_render_dpi == 200
    assert config.ocr_device == "cpu"


@pytest.mark.asyncio
async def test_stop_is_safe_when_never_started(tmp_path: Path) -> None:
    settings = Settings(temp_root=tmp_path / "temp", ocr_enabled=False)
    manager = OcrWorkerManager(settings)
    await manager.stop()
    assert manager.ready is False
