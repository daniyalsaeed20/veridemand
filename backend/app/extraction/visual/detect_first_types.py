"""Types for detector-first (detect separate from recognise) shadow APIs.

Never carry recognised text on detection results. Recognition status is
metadata for corpus tooling — detections are retained regardless of status.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

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

LimitType = Literal["max", "min"]


@dataclass(frozen=True, slots=True)
class DetectorRuntimeParams:
    """Predict-time detector knobs for shadow detect-first runs."""

    thresh: float = 0.30
    box_thresh: float = 0.60
    unclip_ratio: float = 1.50
    limit_side_len: int = 1600
    limit_type: LimitType = "max"

    def to_predict_kwargs(self) -> dict[str, Any]:
        """PaddleX TextDet predict kwargs (unprefixed names)."""

        return {
            "thresh": float(self.thresh),
            "box_thresh": float(self.box_thresh),
            "unclip_ratio": float(self.unclip_ratio),
            "limit_side_len": int(self.limit_side_len),
            "limit_type": str(self.limit_type),
        }

    def validate(self) -> None:
        """Raise ``ValueError`` for invalid or extreme thresholds."""

        if not (0.0 < self.thresh < 1.0):
            raise ValueError(f"thresh out of range: {self.thresh}")
        if not (0.0 < self.box_thresh < 1.0):
            raise ValueError(f"box_thresh out of range: {self.box_thresh}")
        if not (1.0 <= self.unclip_ratio <= 3.0):
            raise ValueError(f"unclip_ratio out of range: {self.unclip_ratio}")
        if self.limit_side_len < 320 or self.limit_side_len > 4096:
            raise ValueError(f"limit_side_len out of range: {self.limit_side_len}")
        if self.limit_type not in {"max", "min"}:
            raise ValueError(f"limit_type invalid: {self.limit_type}")


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
    # Shadow/calibration provenance only — live Phase 4 path never sets these.
    source_detector_names: tuple[str, ...] = ()
    source_confidences: tuple[float, ...] = ()
    merge_version: str | None = None


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
