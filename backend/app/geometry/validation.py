"""Geometry validation helpers for canonical page metadata."""

from __future__ import annotations

import math

from backend.app.geometry.models import NormalisedBoundingBox

_VALID_ROTATIONS = frozenset({0, 90, 180, 270})


def validate_rotation_degrees(rotation: int) -> int:
    """Return ``rotation`` when it is a supported PDF page rotation."""

    if rotation not in _VALID_ROTATIONS:
        raise ValueError("Page rotation must be 0, 90, 180, or 270 degrees.")
    return rotation


def clamp_bbox_to_page(bbox: NormalisedBoundingBox) -> NormalisedBoundingBox:
    """Return a page-contained bounding box, mirroring contract clamp semantics."""

    x = min(max(bbox.x, 0.0), 1.0)
    y = min(max(bbox.y, 0.0), 1.0)
    width = min(max(bbox.width, 0.0), 1.0 - x)
    height = min(max(bbox.height, 0.0), 1.0 - y)
    if width <= 0.0 or height <= 0.0:
        raise ValueError("Bounding box width and height must remain positive after clamp.")
    if any(math.isnan(value) or math.isinf(value) for value in (x, y, width, height)):
        raise ValueError("Bounding box values must be finite.")
    return NormalisedBoundingBox(x=x, y=y, width=width, height=height)
