"""Strict Pydantic schemas for Phase 5 crop dataset tooling.

Manifests intentionally omit OCR text, transcripts, and case names.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPolygon
from backend.app.datasets.phase5.constants import (
    CANDIDATE_SOURCES,
    COVERAGE_ACTIONS,
    COVERAGE_EVENT_VERSION,
    COVERAGE_ISSUE_FLAGS,
    COVERAGE_OUTCOMES,
    COVERAGE_QUEUE_VERSION,
    CROP_PADDING_VERSION,
    CROP_QUALITY_FLAGS,
    HUMAN_LABELS,
    LABEL_SCHEMA_VERSION,
    PILOT_PRIMARY_QUEUE_VERSION,
    PILOT_SAMPLING_VERSION,
    PILOT_SECONDARY_QUEUE_VERSION,
    PILOT_VERSION,
    QUEUE_ALGORITHM_VERSION,
    REVIEW_POLICY_VERSION,
    REVIEW_QUEUE_VERSION,
    SCHEMA_VERSION,
    SOURCE_FAMILIES,
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
SourceFamily = Literal[
    "medical_form",
    "police_form",
    "billing_ledger",
    "fax_record",
    "insurance_letter",
    "image_document",
    "other",
]


class DocumentRecord(ApiModel):
    """Private document registration (opaque IDs; paths stay gitignored)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    document_id: Annotated[str, Field(min_length=8, max_length=64)]
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    source_family: SourceFamily = "other"
    document_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    page_count: Annotated[int, Field(ge=0)]
    # Opaque batch-manifest key (not a filesystem path).
    opaque_label: Annotated[str, Field(min_length=1, max_length=128)]
    # Relative path under fixtures/private/ (private manifests only).
    source_relpath: Annotated[str, Field(min_length=1, max_length=512)]
    created_at: datetime

    @field_validator("source_family")
    @classmethod
    def _family_ok(cls, value: str) -> str:
        if value not in SOURCE_FAMILIES:
            raise ValueError(f"Unknown source_family: {value}")
        return value

    @field_validator("document_sha256")
    @classmethod
    def _hex_sha(cls, value: str) -> str:
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value.lower()):
            raise ValueError("document_sha256 must be 64 lowercase hex characters")
        return value.lower()


class SourceRecord(ApiModel):
    """Private source document / page provenance (opaque IDs only)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    document_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_id: Annotated[str, Field(min_length=8, max_length=64)]
    page_index: Annotated[int, Field(ge=0)]
    page_width_px: Annotated[int, Field(gt=0)] | None = None
    page_height_px: Annotated[int, Field(gt=0)] | None = None
    # Relative path under private phase5 root only (never absolute case paths in reports).
    page_relpath: Annotated[str, Field(min_length=1, max_length=512)] | None = None
    source_family: SourceFamily | None = None
    document_sha256: Annotated[str, Field(min_length=64, max_length=64)] | None = None
    page_count: Annotated[int, Field(ge=0)] | None = None
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
    quality_flags: list[str] = Field(default_factory=list)
    queue_name: Annotated[str, Field(max_length=64)] | None = None
    created_at: datetime

    @field_validator("label")
    @classmethod
    def _label_ok(cls, value: str | None) -> str | None:
        if value is not None and value not in HUMAN_LABELS:
            raise ValueError(f"Unknown label: {value}")
        return value

    @field_validator("quality_flags")
    @classmethod
    def _flags_ok(cls, value: list[str]) -> list[str]:
        for flag in value:
            if flag not in CROP_QUALITY_FLAGS:
                raise ValueError(f"Unknown quality flag: {flag}")
        return value


class ResolvedLabelRecord(ApiModel):
    """Derived label resolution for one crop (recomputable from events)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    status: ResolutionStatus
    label: HumanLabel | None = None
    training_eligible: bool = False
    # Single-pass prototype path (ADR 0053); release training_eligible stays dual-review.
    prototype_model_eligible: bool = False
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


class ReviewQueueEntry(ApiModel):
    """One crop in a blinded primary-review queue (no source metadata for UI)."""

    crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    queue_index: Annotated[int, Field(ge=0)]


class ReviewQueueManifest(ApiModel):
    """Deterministic blinded review queue (gitignored)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    queue_version: str = REVIEW_QUEUE_VERSION
    queue_algorithm_version: str = QUEUE_ALGORITHM_VERSION
    seed: Annotated[int, Field(ge=0)]
    role: Literal["primary", "secondary", "adjudicator"] = "primary"
    queue_name: Literal[
        "pilot-primary",
        "pilot-secondary",
        "full-primary",
        "adjudication",
        "prototype-primary",
    ] = "full-primary"
    authorised_for_review: bool = False
    authorisation_note: Annotated[str, Field(max_length=256)] | None = None
    created_at: datetime
    entries: list[ReviewQueueEntry] = Field(default_factory=list)
    content_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    crop_manifest_sha256: Annotated[str, Field(min_length=64, max_length=64)] | None = None
    source_group_count: Annotated[int, Field(ge=0)] = 0
    candidate_source_counts: dict[str, int] = Field(default_factory=dict)
    # Prototype-queue integrity fields (optional; private manifests only).
    input_pilot_version: Annotated[str, Field(max_length=64)] | None = None
    input_manifest_hashes: dict[str, str] = Field(default_factory=dict)
    excluded_active_coverage_page_count: Annotated[int, Field(ge=0)] | None = None
    source_family_counts: dict[str, int] = Field(default_factory=dict)
    ocr_confidence_sampling: Annotated[str, Field(max_length=128)] | None = None


class PilotCropRecord(ApiModel):
    """One crop selected into the annotation pilot (private; no labels)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    pilot_version: Literal["phase5-annotation-pilot-v1"] = PILOT_VERSION
    sampling_policy_version: Literal["phase5-annotation-pilot-sampling-v1"] = PILOT_SAMPLING_VERSION
    pilot_crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    canonical_crop_id: Annotated[str, Field(min_length=8, max_length=64)]
    crop_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    source_group_id: Annotated[str, Field(min_length=8, max_length=64)]
    opaque_page_reference: Annotated[str, Field(min_length=8, max_length=64)]
    selection_stratum: Annotated[str, Field(min_length=1, max_length=128)]
    sampling_reason: Annotated[str, Field(min_length=1, max_length=256)]
    queue_seed: Annotated[int, Field(ge=0)]
    primary_position: Annotated[int, Field(ge=0)]
    secondary_position: Annotated[int, Field(ge=0)]
    created_at: datetime
    input_manifest_hashes: dict[str, str] = Field(default_factory=dict)
    pilot_manifest_sha256: Annotated[str, Field(min_length=64, max_length=64)] | None = None


class PilotManifest(ApiModel):
    """Aggregate pilot selection record (private)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    pilot_version: Literal["phase5-annotation-pilot-v1"] = PILOT_VERSION
    sampling_policy_version: Literal["phase5-annotation-pilot-sampling-v1"] = PILOT_SAMPLING_VERSION
    created_at: datetime
    target_size: Annotated[int, Field(ge=1)]
    crop_count: Annotated[int, Field(ge=0)]
    pages_represented: Annotated[int, Field(ge=0)]
    source_groups_represented: Annotated[int, Field(ge=0)]
    primary_seed: Annotated[int, Field(ge=0)]
    secondary_seed: Annotated[int, Field(ge=0)]
    primary_queue_version: Literal["phase5-pilot-primary-v1"] = PILOT_PRIMARY_QUEUE_VERSION
    secondary_queue_version: Literal["phase5-pilot-secondary-v1"] = PILOT_SECONDARY_QUEUE_VERSION
    content_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    input_manifest_hashes: dict[str, str] = Field(default_factory=dict)
    stratum_counts: dict[str, int] = Field(default_factory=dict)
    per_page_min: Annotated[int, Field(ge=0)] = 0
    per_page_max: Annotated[int, Field(ge=0)] = 0
    entries: list[PilotCropRecord] = Field(default_factory=list)


class CoverageEvent(ApiModel):
    """Append-only page coverage-review decision (not a script label)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    coverage_event_version: Literal["phase5-coverage-event-v1"] = COVERAGE_EVENT_VERSION
    coverage_event_id: Annotated[str, Field(min_length=8, max_length=64)]
    opaque_page_reference: Annotated[str, Field(min_length=8, max_length=64)]
    opaque_document_reference: Annotated[str, Field(min_length=8, max_length=64)]
    reviewer_id: Annotated[str, Field(min_length=1, max_length=64)]
    action: Literal["resolve", "reopen"] = "resolve"
    outcome: str | None = None
    page_render_hash: Annotated[str, Field(min_length=64, max_length=64)]
    overlay_hash: Annotated[str, Field(min_length=64, max_length=64)]
    supersedes_event_id: Annotated[str, Field(min_length=8, max_length=64)] | None = None
    issue_flags: list[str] = Field(default_factory=list)
    note: Annotated[str, Field(max_length=256)] | None = None
    created_at: datetime

    @field_validator("action")
    @classmethod
    def _action_ok(cls, value: str) -> str:
        if value not in COVERAGE_ACTIONS:
            raise ValueError(f"Unknown coverage action: {value}")
        return value

    @field_validator("outcome")
    @classmethod
    def _outcome_ok(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value in HUMAN_LABELS:
            raise ValueError("script labels are not valid coverage outcomes")
        if value not in COVERAGE_OUTCOMES:
            raise ValueError(f"Unknown coverage outcome: {value}")
        return value

    @field_validator("issue_flags")
    @classmethod
    def _flags_ok(cls, value: list[str]) -> list[str]:
        for flag in value:
            if flag not in COVERAGE_ISSUE_FLAGS:
                raise ValueError(f"Unknown coverage issue flag: {flag}")
        return value

    @field_validator("page_render_hash", "overlay_hash")
    @classmethod
    def _hash_ok(cls, value: str) -> str:
        if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("hash must be 64 lowercase hex characters")
        return value

    @model_validator(mode="after")
    def _resolve_requires_outcome(self) -> CoverageEvent:
        if self.action == "resolve" and self.outcome is None:
            raise ValueError("resolve action requires an outcome")
        if self.action == "reopen" and self.outcome is not None:
            raise ValueError("reopen action must not include an outcome")
        return self


class CoverageQueueEntry(ApiModel):
    """One page in the coverage-review queue."""

    opaque_page_reference: Annotated[str, Field(min_length=8, max_length=64)]
    opaque_document_reference: Annotated[str, Field(min_length=8, max_length=64)]
    queue_index: Annotated[int, Field(ge=0)]
    priority_score: Annotated[int, Field(ge=0)] = 0
    priority_reasons: list[str] = Field(default_factory=list)
    crop_count: Annotated[int, Field(ge=0)] = 0
    skipped_block_gap_count: Annotated[int, Field(ge=0)] = 0


class CoverageQueueManifest(ApiModel):
    """Deterministic coverage-review queue for all pages (gitignored)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    queue_version: Literal["phase5-coverage-queue-v1"] = COVERAGE_QUEUE_VERSION
    created_at: datetime
    page_count: Annotated[int, Field(ge=0)]
    content_sha256: Annotated[str, Field(min_length=64, max_length=64)]
    entries: list[CoverageQueueEntry] = Field(default_factory=list)
    manual_region_status: Literal["not_yet_human_verified"] = "not_yet_human_verified"


class BlockCoverageRecord(ApiModel):
    """Aggregate-safe block→line coverage audit row (opaque refs only)."""

    schema_version: Literal["phase5-dataset-schema-v1"] = SCHEMA_VERSION
    opaque_page_reference: Annotated[str, Field(min_length=8, max_length=64)]
    opaque_document_reference: Annotated[str, Field(min_length=8, max_length=64)]
    block_index: Annotated[int, Field(ge=0)]
    child_line_count: Annotated[int, Field(ge=0)]
    child_crop_exists: bool
    union_coverage_ratio: Annotated[float, Field(ge=0.0, le=1.0)]
    coverage_gap: bool
    requires_human_coverage_review: bool
