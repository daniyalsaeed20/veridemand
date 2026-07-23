"""Real PaddleOCR integration smoke (CPU). Requires bootstrapped models."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODEL_ROOT = ROOT / ".models" / "paddleocr"
RECORD = MODEL_ROOT / "model-record.json"


pytestmark = pytest.mark.skipif(
    not RECORD.is_file(),
    reason="OCR models not bootstrapped (run pnpm models:ocr:bootstrap)",
)


def test_paddle_adapter_warmup_and_recognise() -> None:
    import numpy as np
    from PIL import Image, ImageDraw

    from backend.app.extraction.visual.models import OcrRuntimeConfig
    from backend.app.extraction.visual.paddle_adapter import PaddleOcrAdapter

    config = OcrRuntimeConfig(ocr_model_root=str(MODEL_ROOT))
    adapter = PaddleOcrAdapter(config)
    adapter.load()

    image = Image.new("RGB", (640, 160), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((24, 56), "Invoice Total 123.45", fill=(0, 0, 0))
    lines = adapter.recognise(image)
    image.close()
    # Soft gate: adapter must return a list without crashing.
    assert isinstance(lines, list)
    # Prefer detecting at least one line on clean synthetic text.
    if lines:
        assert all(line.text for line in lines)
        assert all(0.0 <= line.recognition_score <= 1.0 for line in lines)
    del np


def test_worker_uses_combined_paddle_ocr_pipeline_operation() -> None:
    """Real stack uses one combined predict; public op name must match."""

    worker_src = (ROOT / "backend" / "app" / "extraction" / "visual" / "worker.py").read_text(
        encoding="utf-8"
    )
    adapter_src = (
        ROOT / "backend" / "app" / "extraction" / "visual" / "paddle_adapter.py"
    ).read_text(encoding="utf-8")
    assert "paddle_ocr_pipeline" in worker_src
    assert "paddle_text_detection" not in worker_src
    assert "self._ocr.predict(" in adapter_src
