"""Types for detector-first (detect separate from recognise) shadow APIs.

Never carry recognised text on detection results. Recognition status is
metadata for corpus tooling — detections are retained regardless of status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RecognitionStatus = Literal[
    "not_run",
    "recognised",
    "empty",
    "low_confidence",
    "failed",
    "rejected",
]

RECOGNITION_STATUSES: frozenset[str] = frozenset(
    {
        "not_run",
        "recognised",
        "empty",
        "low_confidence",
        "failed",
        "rejected",
    }
)


@dataclass(frozen=True, slots=True)
class DetectedTextRegion:
    """One detector-owned region before recognition (no text)."""

    region_id: str
    page_index: int
    order_index: int
    polygon_px: tuple[tuple[float, float], ...]
    polygon_norm: tuple[tuple[float, float], ...]
    bbox_norm: tuple[float, float, float, float]  # x, y, width, height
    detection_confidence: float
    detector_model_name: str
    detector_version: str | None = None


@dataclass(frozen=True, slots=True)
class RecognisedCropResult:
    """Recognition outcome for a supplied crop (never redetects)."""

    region_id: str
    status: RecognitionStatus
    confidence: float | None
    recognizer_model_name: str
    recognizer_version: str | None = None
    # Internal only — callers must not log or commit this field.
    text: str | None = field(default=None, repr=False)
    failure_reason: str | None = None
