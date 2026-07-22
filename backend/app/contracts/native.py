"""Native PDF extraction and trust-gate contracts (Phase 3).

Accepted pages may expose words and characters. Rejected, absent, errored, or
document-escalation-suppressed pages never include candidate text. Visual
agreement is not evaluated in Phase 3.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import Geometry
from backend.app.contracts.identifiers import DocumentId


class NativePageDecision(StrEnum):
    """Page-level native trust decision."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABSENT = "absent"
    ERROR = "error"
    SUPPRESSED_BY_DOCUMENT_ESCALATION = "suppressed_by_document_escalation"


class SourceMode(StrEnum):
    """Page-level source authority for Phase 3."""

    NATIVE_AUTHORITY = "native_authority"
    VISUAL_AUTHORITY = "visual_authority"
    IMAGE_AUTHORITY = "image_authority"


class DocumentSourcePolicy(StrEnum):
    """Document-level source authority after escalation rules."""

    NATIVE_AUTHORITY = "native_authority"
    MIXED_AUTHORITY = "mixed_authority"
    VISUAL_AUTHORITY = "visual_authority"
    IMAGE_AUTHORITY = "image_authority"


class NativeProcessingStatus(StrEnum):
    """Lifecycle of native extraction for a document."""

    PENDING = "pending"
    INSPECTING = "inspecting"
    EXTRACTING = "extracting"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class VisualAgreementStatus(StrEnum):
    """Visual agreement is deferred until Phase 4 rendering/OCR exist."""

    NOT_EVALUATED_PHASE_3 = "not_evaluated_phase_3"


class RecognitionMethod(StrEnum):
    """How accepted native text was obtained."""

    NATIVE_PDF = "native_pdf"
    CANONICAL_PDF_NATIVE = "canonical_pdf_native"


class RecognitionStatus(StrEnum):
    """Public recognition status for accepted native words."""

    ACCEPTED = "accepted"


class ProvisionalOrderStatus(StrEnum):
    """Extraction order is not final reading order."""

    UNVERIFIED = "unverified"


class PdfPointBox(ApiModel):
    """Top-left PDF-point bounding box preserved alongside normalised geometry."""

    x: float = Field(description="Left edge in PDF points (top-left origin).")
    y: float = Field(description="Top edge in PDF points (top-left origin).")
    width: float = Field(gt=0, description="Width in PDF points.")
    height: float = Field(gt=0, description="Height in PDF points.")
    unit: str = Field(default="pdf_point", description="Always pdf_point.")
    origin: str = Field(default="top_left", description="Always top_left.")

    @field_validator("x", "y", "width", "height")
    @classmethod
    def _finite(cls, value: float) -> float:
        import math

        if math.isnan(value) or math.isinf(value):
            raise ValueError("PDF-point box values must be finite.")
        return value


class NativeCharacter(ApiModel):
    """One accepted native character with canonical geometry."""

    id: str = Field(description="Deterministic character id, e.g. char_p0001_000001.")
    page_number: int = Field(ge=1, description="1-based page number.")
    sequence_index: int = Field(ge=0, description="Provisional extraction sequence index.")
    text: str = Field(min_length=1, description="Character as returned by pdfplumber.")
    normalised_text: str = Field(min_length=1, description="NFC-normalised character text.")
    font_name: str | None = Field(default=None, description="Font name when available.")
    font_size: float = Field(ge=0, description="Font size in PDF points.")
    upright: bool = Field(description="Whether the character is upright.")
    rotation_degrees: float = Field(description="Character rotation in degrees.")
    geometry: Geometry = Field(description="Canonical normalised geometry.")
    pdf_point_bbox: PdfPointBox = Field(description="Top-left PDF-point box.")
    unicode_category: str = Field(description="unicodedata category.")
    is_whitespace: bool = Field(description="Whether the character is whitespace.")


class NativeWord(ApiModel):
    """One accepted native word with canonical geometry."""

    id: str = Field(description="Deterministic word id, e.g. word_p0001_000001.")
    page_number: int = Field(ge=1, description="1-based page number.")
    sequence_index: int = Field(ge=0, description="Provisional extraction sequence index.")
    text: str = Field(min_length=1, description="Word text as extracted.")
    normalised_text: str = Field(min_length=1, description="NFC-normalised word text.")
    character_ids: list[str] = Field(description="Linked accepted character ids.")
    geometry: Geometry = Field(description="Canonical normalised geometry.")
    pdf_point_bbox: PdfPointBox = Field(description="Top-left PDF-point box.")
    font_names: list[str] = Field(default_factory=list, description="Distinct font names.")
    font_sizes: list[float] = Field(default_factory=list, description="Distinct font sizes.")
    upright: bool = Field(description="Whether linked characters are upright.")
    recognition_method: RecognitionMethod = Field(description="Native recognition method.")
    source_mode: SourceMode = Field(description="Must be native_authority when accepted.")
    recognition_status: RecognitionStatus = Field(description="Must be accepted.")


class NativeTrustComponents(ApiModel):
    """Component scores in [0, 1] contributing to the native trust score."""

    character_validity_score: float = Field(ge=0.0, le=1.0)
    geometry_validity_score: float = Field(ge=0.0, le=1.0)
    duplication_score: float = Field(ge=0.0, le=1.0)
    token_structure_score: float = Field(ge=0.0, le=1.0)
    text_density_score: float = Field(ge=0.0, le=1.0)
    order_plausibility_score: float = Field(ge=0.0, le=1.0)
    image_compatibility_score: float = Field(ge=0.0, le=1.0)


class NativePageMetrics(ApiModel):
    """Safe page-level native quality metrics (no extracted text)."""

    raw_character_count: int = Field(ge=0)
    deduplicated_character_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    duplicate_character_ratio: float = Field(ge=0.0, le=1.0)
    replacement_character_ratio: float = Field(ge=0.0, le=1.0)
    control_character_ratio: float = Field(ge=0.0, le=1.0)
    private_use_character_ratio: float = Field(ge=0.0, le=1.0)
    unassigned_character_ratio: float = Field(ge=0.0, le=1.0)
    noncharacter_ratio: float = Field(ge=0.0, le=1.0)
    unprintable_character_ratio: float = Field(ge=0.0, le=1.0)
    cid_token_ratio: float = Field(ge=0.0, le=1.0)
    invalid_geometry_ratio: float = Field(ge=0.0, le=1.0)
    out_of_bounds_character_ratio: float = Field(ge=0.0, le=1.0)
    zero_area_character_ratio: float = Field(ge=0.0, le=1.0)
    invalid_word_geometry_ratio: float = Field(ge=0.0, le=1.0)
    single_character_word_ratio: float = Field(ge=0.0, le=1.0)
    symbol_only_word_ratio: float = Field(ge=0.0, le=1.0)
    alphanumeric_word_ratio: float = Field(ge=0.0, le=1.0)
    very_long_token_ratio: float = Field(ge=0.0, le=1.0)
    repeated_token_ratio: float = Field(ge=0.0, le=1.0)
    whitespace_ratio: float = Field(ge=0.0, le=1.0)
    font_count: int = Field(ge=0)
    missing_font_ratio: float = Field(ge=0.0, le=1.0)
    upright_character_ratio: float = Field(ge=0.0, le=1.0)
    extraction_order_backtrack_ratio: float = Field(ge=0.0, le=1.0)
    characters_per_page_area: float = Field(ge=0.0)
    words_per_page_area: float = Field(ge=0.0)
    image_count: int = Field(ge=0)
    largest_image_area_ratio: float = Field(ge=0.0, le=1.0)
    total_clipped_image_area_ratio: float = Field(ge=0.0, le=1.0)
    page_dimension_match: bool = Field(description="Whether page dims match canonical metadata.")
    components: NativeTrustComponents | None = Field(
        default=None, description="Component scores when calculated."
    )


class NativePageTrustResult(ApiModel):
    """Trust decision for one page (safe; no candidate text)."""

    page_number: int = Field(ge=1)
    decision: NativePageDecision
    source_mode: SourceMode
    native_text_present: bool
    native_trust_score: float | None = Field(default=None, ge=0.0, le=1.0)
    trust_policy_version: str
    hard_rejection: bool
    reason_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    metrics: NativePageMetrics
    visual_agreement_status: VisualAgreementStatus = VisualAgreementStatus.NOT_EVALUATED_PHASE_3
    visual_agreement_score: float | None = Field(default=None)
    native_result_available: bool
    visual_processing_required: bool


class NativeWarning(ApiModel):
    """Safe diagnostic warning without extracted text."""

    code: str = Field(description="Stable reason or warning code.")
    message: str = Field(description="Generic, non-sensitive message.")
    page_number: int | None = Field(default=None, ge=1)


class NativePageResult(ApiModel):
    """Public per-page native result."""

    page_number: int = Field(ge=1)
    decision: NativePageDecision
    source_mode: SourceMode
    trust: NativePageTrustResult
    provisional_order_status: ProvisionalOrderStatus = ProvisionalOrderStatus.UNVERIFIED
    words: list[NativeWord] = Field(default_factory=list)
    characters: list[NativeCharacter] = Field(default_factory=list)
    provisional_native_text: str | None = Field(
        default=None,
        description="Derived only from accepted words; null when not accepted.",
    )
    warnings: list[NativeWarning] = Field(default_factory=list)


class NativeProgress(ApiModel):
    """Monotonic native-stage progress (capped at Phase 3 maximum)."""

    percent: Annotated[int, Field(ge=0, le=35)]
    pages_completed: int = Field(ge=0)
    pages_total: int = Field(ge=0)


class NativeDocumentSummary(ApiModel):
    """Public native-extraction summary for a document."""

    document_id: DocumentId
    native_processing_status: NativeProcessingStatus
    document_source_policy: DocumentSourcePolicy | None = None
    trust_policy_version: str
    page_count: int = Field(ge=0)
    pages_accepted: int = Field(ge=0)
    pages_rejected: int = Field(ge=0)
    pages_absent: int = Field(ge=0)
    pages_errored: int = Field(ge=0)
    pages_suppressed: int = Field(ge=0)
    native_result_available: bool
    visual_processing_required: bool
    native_extraction_performed: bool
    final_result_available: bool = Field(default=False)
    progress: NativeProgress
    page_decisions: list[NativePageTrustResult] = Field(default_factory=list)
    warnings: list[NativeWarning] = Field(default_factory=list)
    created_at: datetime
    user_status_message: str | None = Field(
        default=None,
        description="Safe user-facing status based on document source policy.",
    )
