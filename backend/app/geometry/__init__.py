"""Normalised geometry helpers for Phase 2 canonical coordinates."""

from backend.app.geometry.models import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPoint,
    NormalisedPolygon,
    phase2_alignment_geometry,
)
from backend.app.geometry.rotation import rotate_normalised_point
from backend.app.geometry.validation import (
    clamp_bbox_to_page,
    validate_rotation_degrees,
)

__all__ = [
    "Geometry",
    "NormalisedBoundingBox",
    "NormalisedPoint",
    "NormalisedPolygon",
    "clamp_bbox_to_page",
    "phase2_alignment_geometry",
    "rotate_normalised_point",
    "validate_rotation_degrees",
]
