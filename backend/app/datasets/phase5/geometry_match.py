"""Geometry matching helpers for detector-first corpus tooling."""

from __future__ import annotations

from backend.app.contracts.geometry import NormalisedBoundingBox


def bbox_area(bbox: NormalisedBoundingBox) -> float:
    return float(bbox.width) * float(bbox.height)


def bbox_intersection_area(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> float:
    ax0, ay0 = a.x, a.y
    ax1, ay1 = a.x + a.width, a.y + a.height
    bx0, by0 = b.x, b.y
    bx1, by1 = b.x + b.width, b.y + b.height
    ix0 = max(ax0, bx0)
    iy0 = max(ay0, by0)
    ix1 = min(ax1, bx1)
    iy1 = min(ay1, by1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    return float((ix1 - ix0) * (iy1 - iy0))


def bbox_iou(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> float:
    inter = bbox_intersection_area(a, b)
    if inter <= 0.0:
        return 0.0
    union = bbox_area(a) + bbox_area(b) - inter
    if union <= 0.0:
        return 0.0
    return float(inter / union)


def bbox_l_inf(a: NormalisedBoundingBox, b: NormalisedBoundingBox) -> float:
    return max(
        abs(a.x - b.x),
        abs(a.y - b.y),
        abs(a.width - b.width),
        abs(a.height - b.height),
    )


def bbox_from_tuple(values: tuple[float, float, float, float]) -> NormalisedBoundingBox:
    return NormalisedBoundingBox(x=values[0], y=values[1], width=values[2], height=values[3])


def containment_ratio(inner: NormalisedBoundingBox, outer: NormalisedBoundingBox) -> float:
    """Fraction of ``inner`` area covered by intersection with ``outer``."""

    area = bbox_area(inner)
    if area <= 0.0:
        return 0.0
    return float(bbox_intersection_area(inner, outer) / area)
