"""Strict Pydantic schemas for Phase 5 crop dataset tooling.

Manifests intentionally omit OCR text, transcripts, and case names.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPolygon
from backend.app.datasets.phase5.constants import (
    CANDIDATE_SOURCES,
    CROP_PADDING_VERSION,
    HUMAN_LABELS,
    LABEL_SCHEMA_VERSION,
    REVIEW_POLICY_VERSION,
    SCHEMA_VERSION,
    SPLIT_ALGORITHM_VERSION,
)

HumanLabel = Literal["printed", "handwritten", "uncertain", "non_text"]
CandidateSource = Literal[
    "visual_detection",
    "full_page_ocr",
    "targeted_repair",
    "heuristic_region",
    "noise_region",
    "manual_region",
    "synthetic_negative",
]
ReviewerRole = Literal["primary", "secondary", "adjudicator"]
ReviewAction = Literal["label", "skip", "exclude", "flag_quality", "undo_mark"]
ResolutionStatus = Literal[
    "unreviewed",
    "single_review",
    "agreed",
    "conflict",
    "adjudicated",
    "excluded",
    "invalidated_hash_mismatch",
]
SplitName = Literal["train", "val", "test", "held_out"]


class SourceRecord(ApiModel):
    """Private source document / page provenance (opaque IDs only)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    document_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_index: Annotated[int, Field(ge=0)]
    page_width_px: Annotated[int, Field(gt=0)] | None = None
    page_height_px: Annotated[int, Field(gt=0)] | None = None
    # Relative path under private root only (never absolute case paths in reports).
    page_relpath: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    created_at: datetime


class AppliedPadding(ApiModel):
    """Record of deterministic crop padding (policy version + ratios)."""

    policy_version: Literal["phase5-crop-pad-v1"] = CROP_PADDING_VERSION
    pad_ratio: Annotated[float, Field(ge=0.0, le=0.5)]
    pad_x: Annotated[float, Field(ge=0.0, le=1.0)]
    pad_y: Annotated[float, Field(ge=0.0, le=1.0)]
    clamped: bool = False


class CropRecord(ApiModel):
    """One exported region crop (geometry + hashes; no text)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    document_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_index: Annotated[int, Field(ge=0)]
    candidate_source: CandidateSource
    # Source geometry before padding (authoritative local coordinates).
    source_bbox: NormalisedBoundingBox
    source_polygon: NormalisedPolygon | None = None
    # Crop window after padding + clamp (written image bounds).
    crop_bbox: NormalisedBoundingBox
    applied_padding: AppliedPadding
    crop_relpath: Annotated[str, Field(min_length=1, max_length=512)]
    sha256: Annotated[str, Field(min_length=64, max_length=64)]
    perceptual_hash: Annotated[str, Field(min_length=16, max_length=16)]
    width_px: Annotated[int, Field(gt=0)]
    height_px: Annotated[int, Field(gt=0)]
    duplicate_family_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None
    created_at: datetime

    @field_validator("candidate_source")
    @classmethod
    def _known_source(cls, value: str) -> str:
        if value not in CANDIDATE_SOURCES:
            raise ValueError(f"Unknown candidate_source: {value}")
        return value

    @field_validator("sha256")
    @classmethod
    def _hex_sha(cls, value: str) -> str:
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value.lower()):
            raise ValueError("sha256 must be 64 lowercase hex characters")
        return value.lower()


class ReviewEvent(ApiModel):
    """Append-only human review event (blind labelling audit trail)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    label_schema_version: Literal["phase5-human-label-v1"] = LABEL_SCHEMA_VERSION
    review_policy_version: Literal["phase5-review-policy-v1"] = REVIEW_POLICY_VERSION
    review_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    reviewer_id: Annotated[str, Field(min_length=1, max_length=64)]
    role: ReviewerRole
    action: ReviewAction
    label: HumanLabel | None = None
    note: Annotated[str, Field(max_length=256)] | None = None
    created_at: datetime

    @field_validator("label")
    @classmethod
    def _label_ok(cls, value: str | None) -> str | None:
        if value is not None and value not in HUMAN_LABELS:
            raise ValueError(f"Unknown label: {value}")
        return value


class ResolvedLabelRecord(ApiModel):
    """Derived label resolution for one crop (recomputable from events)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    status: ResolutionStatus
    label: HumanLabel | None = None
    training_eligible: bool = False
    primary_label: HumanLabel | None = None
    secondary_label: HumanLabel | None = None
    adjudicator_label: HumanLabel | None = None
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    duplicate_family_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None
    resolved_at: datetime


class ExclusionRecord(ApiModel):
    """Explicit exclusion from training / splits."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    exclusion_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    reason: Annotated[str, Field(min_length=1, max_length=256)]
    created_at: datetime


class DuplicateFamilyRecord(ApiModel):
    """Exact SHA-256 duplicate family (perceptual near-dups are warnings only)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    duplicate_family_id: Annotated[str, Field(min_length=8, max_length=64)]
    sha256: Annotated[str, Field(min_length=64, max_length=64)]
    crop_ids: list[Annotated[str, Field(min_length=8, max_length=64)]] = Field(min_length=1)


class SplitAssignment(ApiModel):
    """One crop assignment in a frozen split manifest."""

    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    split: SplitName
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    duplicate_family_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None


class SplitManifest(ApiModel):
    """Group-aware train/val/test/held-out assignment."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    split_algorithm_version: Literal["phase5-group-split-v1"] = SPLIT_ALGORITHM_VERSION
    seed: Annotated[int, Field(ge=0)]
    created_at: datetime
    assignments: list[SplitAssignment] = Field(default_factory=list)
    content_sha256: Annotated[str, Field(min_length=64, max_length=64)] | None = None
