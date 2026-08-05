"""Detector-first region schemas (private; no OCR text)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPolygon
from backend.app.datasets.phase5.constants import (
    DETECTOR_FIRST_CORPUS_VERSION,
    DETECTOR_FIRST_LABEL_TRANSFER_VERSION,
    HUMAN_LABELS,
)
from backend.app.datasets.phase5.schemas import AppliedPadding

RecognitionStatusLiteral = Literal[
    "not_run",
    "recognised",
    "empty",
    "low_confidence",
    "failed",
    "rejected",
]

ConfidenceBand = Literal["none", "rejected", "low", "mid", "high"]

LabelTransferMethod = Literal["exact_crop_sha256", "strict_geometry"]

SeedCoverageKind = Literal[
    "exact",
    "near_exact",
    "contained",
    "fragmented",
    "missed",
]


class DetectorFirstRegionRecord(ApiModel):
    """One detector-first crop region (geometry + hashes + recognition status)."""

    schema_version: Literal["phase5-detector-first-regions-v1"] = DETECTOR_FIRST_CORPUS_VERSION
    region_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    document_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_index: Annotated[int, Field(ge=0)]
    order_index: Annotated[int, Field(ge=0)]
    source_bbox: NormalisedBoundingBox
    source_polygon: NormalisedPolygon | None = None
    crop_bbox: NormalisedBoundingBox
    applied_padding: AppliedPadding
    crop_relpath: Annotated[str, Field(min_length=1, max_length=512)]
    crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    page_render_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    perceptual_hash: Annotated[str, Field(min_length=16, max_length=16)]
    width_px: Annotated[int, Field(gt=0)]
    height_px: Annotated[int, Field(gt=0)]
    detection_confidence: Annotated[float, Field(ge=0.0, le=1.0)]
    detector_model_name: Annotated[str, Field(min_length=1, max_length=128)]
    recognition_status: RecognitionStatusLiteral = "not_run"
    recognition_confidence_band: ConfidenceBand = "none"
    duplicate_of_region_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None
    created_at: datetime

    @field_validator("crop_sha256", "page_render_sha256")
    @classmethod
    def _hex_sha(cls, value: str) -> str:
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value.lower()):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        return value.lower()


class DetectorFirstLabelTransferRecord(ApiModel):
    """Private provenance for a label transferred onto a detector-first crop."""

    schema_version: Literal["phase5-detector-first-label-transfer-v1"] = (
        DETECTOR_FIRST_LABEL_TRANSFER_VERSION
    )
    new_crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    old_crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    method: LabelTransferMethod
    overlap_score: Annotated[float, Field(ge=0.0, le=1.0)]
    label: Literal["printed", "handwritten", "uncertain", "non_text"]
    label_provenance: Annotated[str, Field(min_length=1, max_length=128)]
    created_at: datetime

    @field_validator("label")
    @classmethod
    def _label_ok(cls, value: str) -> str:
        if value not in HUMAN_LABELS:
            raise ValueError(f"Unknown label: {value}")
        return value


def confidence_band(confidence: float | None, *, low_thr: float, min_thr: float) -> ConfidenceBand:
    if confidence is None:
        return "none"
    if confidence < min_thr:
        return "rejected"
    if confidence < low_thr:
        return "low"
    if confidence < 0.90:
        return "mid"
    return "high"
