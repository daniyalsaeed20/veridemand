"""Lightweight image preprocessing for OCR retry (FR-EXT-04).

Records deskew affine so OCR polygons can be mapped back to the
pre-deskew (canonical render) image space.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


@dataclass(frozen=True)
class PreprocessResult:
    image: Image.Image
    path_name: str  # identity | grayscale_contrast | deskew_grayscale_contrast
    # Forward affine (2x3) mapping canonical-render coords → processed image.
    # Inverse is applied to OCR polygons before normalize.
    forward_affine: tuple[float, float, float, float, float, float] | None = None


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
        return PreprocessResult(image=image.copy(), path_name="identity", forward_affine=None)

    gray = ImageOps.grayscale(image)
    enhanced = ImageEnhance.Contrast(gray).enhance(1.4)
    rgb = Image.merge("RGB", (enhanced, enhanced, enhanced))

    deskewed, used_deskew, affine = _light_deskew(rgb)
    path = "deskew_grayscale_contrast" if used_deskew else "grayscale_contrast"
    return PreprocessResult(image=deskewed, path_name=path, forward_affine=affine)


def invert_polygon_affine(
    polygon_px: list[tuple[float, float]],
    forward_affine: tuple[float, float, float, float, float, float] | None,
) -> list[tuple[float, float]]:
    """Map OCR polygons from processed image space back to canonical render space."""
    if forward_affine is None:
        return polygon_px
    inv = _invert_affine(forward_affine)
    if inv is None:
        return polygon_px
    a, b, c, d, e, f = inv
    out: list[tuple[float, float]] = []
    for x, y in polygon_px:
        out.append((a * x + b * y + c, d * x + e * y + f))
    return out


def _invert_affine(
    forward: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float] | None:
    a, b, c, d, e, f = forward
    det = a * e - b * d
    if abs(det) < 1e-9:
        return None
    ia = e / det
    ib = -b / det
    id_ = -d / det
    ie = a / det
    ic = -(ia * c + ib * f)
    iff = -(id_ * c + ie * f)
    return (ia, ib, ic, id_, ie, iff)


def _light_deskew(
    image: Image.Image,
) -> tuple[Image.Image, bool, tuple[float, float, float, float, float, float] | None]:
    try:
        import cv2
    except ImportError:
        return image, False, None

    arr = np.asarray(image.convert("L"))
    _, binary = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(binary)
    if coords is None or len(coords) < 50:
        return image, False, None
    rect = cv2.minAreaRect(coords)
    angle = rect[-1]
    if angle < -45:
        angle = 90 + angle
    if abs(angle) < 0.5 or abs(angle) > 15.0:
        return image, False, None
    h, w = arr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rotated = cv2.warpAffine(
        np.asarray(image.convert("RGB")),
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REPLICATE,
    )
    # OpenCV 2x3: [[a,b,c],[d,e,f]]
    affine = (
        float(matrix[0, 0]),
        float(matrix[0, 1]),
        float(matrix[0, 2]),
        float(matrix[1, 0]),
        float(matrix[1, 1]),
        float(matrix[1, 2]),
    )
    return Image.fromarray(rotated), True, affine
