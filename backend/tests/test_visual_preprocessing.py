"""Unit tests for visual preprocessing helpers."""

from __future__ import annotations

from PIL import Image

from backend.app.contracts.ocr import PreprocessingVariant
from backend.app.extraction.visual.preprocessing import prepare_grayscale_fallback, prepare_primary


def test_prepare_primary_returns_rgb() -> None:
    image = Image.new("RGBA", (32, 16), (255, 255, 255, 128))
    prepared, variant = prepare_primary(image)
    assert prepared.mode == "RGB"
    assert variant is PreprocessingVariant.ORIGINAL_RGB


def test_prepare_grayscale_fallback_returns_rgb() -> None:
    image = Image.new("RGB", (32, 16), (40, 40, 40))
    prepared, variant = prepare_grayscale_fallback(image)
    assert prepared.mode == "RGB"
    assert variant is PreprocessingVariant.GRAYSCALE_AUTOCONTRAST
