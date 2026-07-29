"""Targeted regional OCR repair contracts (Phase 4 Correction 6).

Privacy-safe aggregates only — never include recognised strings, crop paths,
or private document identifiers.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import NormalisedBoundingBox

REPAIR_POLICY_VERSION = "phase4-targeted-repair-v1"


class RepairMethod(StrEnum):
    """How a bounded repair region is processed."""

    RECOGNITION_ONLY = "recognition_only"
    LOCAL_DETECTION_AND_RECOGNITION = "local_detection_and_recognition"


class RepairQualityStatus(StrEnum):
    """Outcome of the targeted-repair quality gate."""

    REPAIR_COMPLETE = "repair_complete"
    REPAIR_COMPLETE_WITH_WARNINGS = "repair_complete_with_warnings"
    REPAIR_INSUFFICIENT = "repair_insufficient"
    REPAIR_FAILED = "repair_failed"


class WordRetentionClass(StrEnum):
    """Classification of a base word relative to repair regions."""

    RETAINED = "retained"
    SUPPRESSED_FOR_REPAIR = "suppressed_for_repair"
    OVERLAPS_REPAIR_REGION = "overlaps_repair_region"
    QUARANTINED = "quarantined"
    UNAFFECTED = "unaffected"


class WordProvenanceKind(StrEnum):
    """Per-word source provenance for public repaired pages."""

    NATIVE_PDF_WORD = "native_pdf_word"
    VERIFIED_EMBEDDED_OCR_WORD = "verified_embedded_ocr_word"
    TARGETED_REPAIR_RECOGNITION_WORD = "targeted_repair_recognition_word"
    TARGETED_REPAIR_LOCAL_OCR_WORD = "targeted_repair_local_ocr_word"
    PRINTED_VISUAL_OCR_WORD = "printed_visual_ocr_word"


class BaseSourceMode(StrEnum):
    """Trusted base result used as the repair starting point."""

    NATIVE = "native"
    VERIFIED_EMBEDDED = "verified_embedded"


class RepairRegionRecord(ApiModel):
    """One bounded failed region selected for local repair."""

    repair_region_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    source_word_ids: list[str] = Field(default_factory=list)
    normalised_bbox: NormalisedBoundingBox
    expanded_normalised_bbox: NormalisedBoundingBox
    page_coverage_ratio: float = Field(ge=0.0, le=1.0)
    failure_reason_codes: list[str] = Field(default_factory=list)
    repair_method: RepairMethod
    policy_version: str = Field(default=REPAIR_POLICY_VERSION, min_length=1)

    @field_validator("failure_reason_codes", "source_word_ids")
    @classmethod
    def _no_blanks(cls, value: list[str]) -> list[str]:
        return [item for item in value if item and item.strip()]


class TargetedRepairEligibilityEvidence(ApiModel):
    """Typed, versioned evidence for targeted-repair eligibility."""

    page_number: int = Field(ge=1)
    base_source_mode: BaseSourceMode

    candidate_word_count: int = Field(ge=0)
    verified_word_count: int = Field(ge=0)
    failed_word_count: int = Field(ge=0)

    failed_region_count: int = Field(ge=0)
    failed_region_coverage_ratio: float = Field(ge=0.0, le=1.0)
    largest_region_coverage_ratio: float = Field(ge=0.0, le=1.0)

    retained_page_coverage_ratio: float = Field(ge=0.0, le=1.0)
    visual_agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)
    recognition_agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)

    repair_eligible: bool
    repair_method: RepairMethod | None = None
    repair_reason_codes: list[str] = Field(default_factory=list)

    full_ocr_fallback_required: bool
    policy_version: str = Field(default=REPAIR_POLICY_VERSION, min_length=1)

    @field_validator("repair_reason_codes")
    @classmethod
    def _no_blank_codes(cls, value: list[str]) -> list[str]:
        return [item for item in value if item and item.strip()]

    @model_validator(mode="after")
    def _consistency(self) -> TargetedRepairEligibilityEvidence:
        if self.repair_eligible and self.full_ocr_fallback_required:
            raise ValueError(
                "repair_eligible and full_ocr_fallback_required are mutually exclusive."
            )
        if self.repair_eligible and self.repair_method is None:
            raise ValueError("Eligible repair requires an explicit repair_method.")
        if not self.repair_eligible and self.repair_method is not None:
            raise ValueError("Ineligible repair must not set repair_method.")
        return self


class RepairRegionExecutionDiagnostics(ApiModel):
    """Privacy-safe per-region execution diagnostics."""

    repair_region_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    method: RepairMethod
    crop_width: int = Field(ge=0)
    crop_height: int = Field(ge=0)
    detector_limit_side: int | None = Field(default=None, ge=0)
    recognition_batch_size: int = Field(default=1, ge=1)
    duration_ms: int = Field(default=0, ge=0)
    result_count: int = Field(default=0, ge=0)
    quality_status: RepairQualityStatus | None = None
    reason_codes: list[str] = Field(default_factory=list)


class RepairQualityEvidence(ApiModel):
    """Typed evidence for the repair quality gate."""

    page_number: int = Field(ge=1)
    status: RepairQualityStatus
    mean_recognition_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    geometry_valid_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    repaired_word_count: int = Field(default=0, ge=0)
    region_coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    remaining_unsupported_ink_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    duplicate_overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    neighbour_agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)
    fragmentation_score: float = Field(default=0.0, ge=0.0, le=1.0)
    low_confidence_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    reason_codes: list[str] = Field(default_factory=list)
    policy_version: str = Field(default=REPAIR_POLICY_VERSION, min_length=1)
    fallback_to_full_ocr: bool = False


class TargetedRepairPageSummary(ApiModel):
    """Aggregate counts published with a repaired page result."""

    retained_native_words: int = Field(default=0, ge=0)
    retained_embedded_words: int = Field(default=0, ge=0)
    repaired_words: int = Field(default=0, ge=0)
    suppressed_words: int = Field(default=0, ge=0)
    repair_regions: int = Field(default=0, ge=0)
    repair_quality_status: RepairQualityStatus | None = None
    repair_method: RepairMethod | None = None
