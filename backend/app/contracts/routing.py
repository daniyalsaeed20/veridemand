"""Page-level hybrid extraction routing contracts (Phase 4.5).

Route decisions never include document text. Metrics are privacy-safe aggregates.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from backend.app.contracts.base import ApiModel


class PageRoute(StrEnum):
    """Cheapest trustworthy processing path selected for one page."""

    DIGITAL_NATIVE = "digital_native"
    EMBEDDED_OCR_VERIFIED = "embedded_ocr_verified"
    EMBEDDED_OCR_TARGETED_REPAIR = "embedded_ocr_targeted_repair"
    FULL_VISUAL_OCR = "full_visual_ocr"
    VISUAL_NO_TEXT = "visual_no_text"
    PAGE_FAILED = "page_failed"
    PAGE_CANCELLED = "page_cancelled"


class PageRouteDecisionStatus(StrEnum):
    """Lifecycle of a page route decision."""

    DECIDED = "decided"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class EstimateStatus(StrEnum):
    """Backend ETA availability for live progress display."""

    UNAVAILABLE = "unavailable"
    COLLECTING_SAMPLES = "collecting_samples"
    AVAILABLE = "available"
    RECALCULATING = "recalculating"
    STALE = "stale"
    COMPLETE = "complete"


class EstimatedCostClass(StrEnum):
    """Relative cost class for a chosen route (diagnostics only)."""

    NEGLIGIBLE = "negligible"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PageRouteDecision(ApiModel):
    """Deterministic, text-free page routing decision."""

    page_number: int = Field(ge=1)
    route: PageRoute
    decision_status: PageRouteDecisionStatus = PageRouteDecisionStatus.DECIDED
    decision_version: str = Field(min_length=1)
    reason_codes: list[str] = Field(default_factory=list)

    native_text_present: bool = False
    native_text_accepted: bool = False
    native_word_count: int = Field(default=0, ge=0)
    native_character_count: int = Field(default=0, ge=0)
    native_trust_score: float | None = Field(default=None, ge=0.0, le=1.0)

    page_image_dominant: bool = False
    embedded_ocr_candidate: bool = False
    visual_agreement_evaluated: bool = False
    visual_agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)

    sampled_box_count: int = Field(default=0, ge=0)
    visible_box_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    recognition_sample_count: int = Field(default=0, ge=0)
    recognition_agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)

    targeted_region_count: int = Field(default=0, ge=0)
    full_ocr_required: bool = False

    estimated_cost_class: EstimatedCostClass = EstimatedCostClass.MEDIUM
    actual_duration_ms: int | None = Field(default=None, ge=0)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("reason_codes", "warnings")
    @classmethod
    def _no_blank_codes(cls, value: list[str]) -> list[str]:
        return [item for item in value if item and item.strip()]


class RepairRegionDiagnostics(ApiModel):
    """Privacy-safe targeted-repair diagnostics (no crops or text)."""

    repair_region_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    repair_method: str = Field(min_length=1)
    source_box_count: int = Field(ge=0)
    crop_width: int = Field(default=0, ge=0)
    crop_height: int = Field(default=0, ge=0)
    recognition_count: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)
    replacement_count: int = Field(default=0, ge=0)
    reason_codes: list[str] = Field(default_factory=list)


class FastOcrPassDiagnostics(ApiModel):
    """Primary/fallback detector-side diagnostics for full visual OCR."""

    primary_limit_side: int = Field(gt=0)
    primary_duration_ms: int = Field(default=0, ge=0)
    primary_detection_count: int = Field(default=0, ge=0)
    primary_average_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    fallback_used: bool = False
    fallback_reason: str | None = None
    fallback_limit_side: int | None = Field(default=None, gt=0)
    fallback_duration_ms: int | None = Field(default=None, ge=0)


class DocumentRouteBreakdown(ApiModel):
    """Aggregate route counts for progress UI (no text)."""

    document_pages_total: int = Field(default=0, ge=0)
    native_pages_retained: int = Field(default=0, ge=0)
    embedded_ocr_pages_verified: int = Field(default=0, ge=0)
    targeted_repair_pages_selected: int = Field(default=0, ge=0)
    targeted_repair_pages_completed: int = Field(default=0, ge=0)
    full_ocr_pages_selected: int = Field(default=0, ge=0)
    full_ocr_pages_completed: int = Field(default=0, ge=0)
    full_ocr_pages_remaining: int = Field(default=0, ge=0)
    visual_no_text_pages: int = Field(default=0, ge=0)
