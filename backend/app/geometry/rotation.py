"""Clockwise rotation of normalised top-left page coordinates."""

from __future__ import annotations

from backend.app.geometry.models import NormalisedPoint
from backend.app.geometry.validation import validate_rotation_degrees


def rotate_normalised_point(point: NormalisedPoint, rotation_degrees: int) -> NormalisedPoint:
    """Rotate a normalised point clockwise by ``rotation_degrees``.

    Supported mappings (clockwise, top-left origin):

    - 0°: ``(x, y)``
    - 90°: ``(1 - y, x)``
    - 180°: ``(1 - x, 1 - y)``
    - 270°: ``(y, 1 - x)``
    """

    rotation = validate_rotation_degrees(rotation_degrees)
    x, y = point.x, point.y
    match rotation:
        case 0:
            return NormalisedPoint(x=x, y=y)
        case 90:
            return NormalisedPoint(x=1.0 - y, y=x)
        case 180:
            return NormalisedPoint(x=1.0 - x, y=1.0 - y)
        case 270:
            return NormalisedPoint(x=y, y=1.0 - x)
        case _:
            raise ValueError("Unsupported rotation.")
