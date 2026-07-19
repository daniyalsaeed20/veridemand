"""Lightweight image preprocessing for OCR retry (FR-EXT-04)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


@dataclass(frozen=True)
class PreprocessResult:
    image: Image.Image
    path_name: str  # recorded provenance: identity | grayscale_contrast | deskew_light


def maybe_preprocess(
    image: Image.Image,
    *,
    force: bool = False,
    low_contrast: bool = False,
) -> PreprocessResult:
    """Apply a single lightweight transform when warranted.

    First-pass OCR uses the original render (identity). Retry path may request
    grayscale + mild contrast, optionally with a light deskew when OpenCV can
    estimate a small skew angle.
    """
    if not force and not low_contrast:
        return PreprocessResult(image=image.copy(), path_name="identity")

    gray = ImageOps.grayscale(image)
    enhanced = ImageEnhance.Contrast(gray).enhance(1.4)
    rgb = Image.merge("RGB", (enhanced, enhanced, enhanced))

    deskewed, used_deskew = _light_deskew(rgb)
    path = "deskew_grayscale_contrast" if used_deskew else "grayscale_contrast"
    return PreprocessResult(image=deskewed, path_name=path)


def _light_deskew(image: Image.Image) -> tuple[Image.Image, bool]:
    try:
        import cv2
    except ImportError:
        return image, False

    arr = np.asarray(image.convert("L"))
    # Invert so text is white-ish for minAreaRect heuristics on dark text
    _, binary = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(binary)
    if coords is None or len(coords) < 50:
        return image, False
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    # Only correct mild skew; avoid large rotations that need separate page rotation metadata
    if abs(angle) < 0.5 or abs(angle) > 15.0:
        return image, False
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(
        np.asarray(image.convert("RGB")),
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return Image.fromarray(rotated), True
