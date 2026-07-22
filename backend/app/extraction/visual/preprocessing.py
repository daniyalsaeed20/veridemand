"""Conservative preprocessing variants for printed OCR."""

from __future__ import annotations

from backend.app.contracts.ocr import PreprocessingVariant
from backend.app.extraction.visual.renderer import flatten_to_rgb
from PIL import Image, ImageOps


def prepare_primary(image: Image.Image) -> tuple[Image.Image, PreprocessingVariant]:
    """Return RGB white-flattened image for the primary OCR pass."""

    rgb = flatten_to_rgb(image)
    return rgb, PreprocessingVariant.ORIGINAL_RGB


def prepare_grayscale_fallback(image: Image.Image) -> tuple[Image.Image, PreprocessingVariant]:
    """Return modest autocontrast grayscale (as RGB) for a single fallback pass."""

    rgb = flatten_to_rgb(image)
    gray = ImageOps.grayscale(rgb)
    contrasted = ImageOps.autocontrast(gray, cutoff=1)
    return contrasted.convert("RGB"), PreprocessingVariant.GRAYSCALE_AUTOCONTRAST
