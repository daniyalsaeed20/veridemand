"""Re-exports of contract geometry models used by canonicalisation."""

from backend.app.contracts.geometry import (
    Geometry,
    NormalisedBoundingBox,
    NormalisedPoint,
    NormalisedPolygon,
    phase2_alignment_geometry,
)

__all__ = [
    "Geometry",
    "NormalisedBoundingBox",
    "NormalisedPoint",
    "NormalisedPolygon",
    "phase2_alignment_geometry",
]
