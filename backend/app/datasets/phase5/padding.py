"""Deterministic crop padding and geometry helpers (phase5-crop-pad-v1)."""

from __future__ import annotations

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.constants import CROP_PADDING_RATIO, CROP_PADDING_VERSION
from backend.app.datasets.phase5.schemas import AppliedPadding


def apply_crop_padding(
    bbox: NormalisedBoundingBox,
    *,
    pad_ratio: float = CROP_PADDING_RATIO,
) -> tuple[NormalisedBoundingBox, AppliedPadding]:
    """Expand bbox by ``pad_ratio`` of max(width, height), clamp to page.

    Source geometry is unchanged; only the derivative crop window is padded.
    """

    if pad_ratio < 0.0 or pad_ratio > 0.5:
        raise ValueError("pad_ratio must be in [0, 0.5]")
    side = max(bbox.width, bbox.height)
    pad = side * pad_ratio
    x0 = bbox.x - pad
    y0 = bbox.y - pad
    x1 = bbox.x + bbox.width + pad
    y1 = bbox.y + bbox.height + pad
    clamped = x0 < 0.0 or y0 < 0.0 or x1 > 1.0 or y1 > 1.0
    x0 = max(0.0, min(x0, 1.0 - 1e-9))
    y0 = max(0.0, min(y0, 1.0 - 1e-9))
    x1 = max(x0 + 1e-9, min(x1, 1.0))
    y1 = max(y0 + 1e-9, min(y1, 1.0))
    crop = NormalisedBoundingBox(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
    applied = AppliedPadding(
        policy_version=CROP_PADDING_VERSION,
        pad_ratio=pad_ratio,
        pad_x=pad,
        pad_y=pad,
        clamped=clamped,
    )
    return crop, applied


def bbox_from_polygon_points(
    points: list[tuple[float, float]],
) -> NormalisedBoundingBox:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    return NormalisedBoundingBox(x=x0, y=y0, width=max(x1 - x0, 1e-6), height=max(y1 - y0, 1e-6))
