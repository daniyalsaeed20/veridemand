"""Native PDF extraction and trust-gate contracts (Phase 3).

Accepted pages may expose words and characters. Rejected, absent, errored, or
document-escalation-suppressed pages never include accepted candidate text in
``words`` / ``characters`` / ``provisional_native_text``. They may retain
``verification_words`` (diagnostic / Phase 4.5 only; recognition_status=rejected).
Visual agreement is not evaluated in Phase 3.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import Geometry
from backend.app.contracts.identifiers import DocumentId

DUPLICATE_LAYER_POLICY_VERSION = "phase3-v1.6"


class NativePageDecision(StrEnum):
    """Page-level native trust decision."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABSENT = "absent"
    ERROR = "error"
    SUPPRESSED_BY_DOCUMENT_ESCALATION = "suppressed_by_document_escalation"


class SourceMode(StrEnum):
    """Page-level source authority for Phase 3+."""

    NATIVE_AUTHORITY = "native_authority"
    EMBEDDED_OCR_AUTHORITY = "embedded_ocr_authority"
    VISUAL_AUTHORITY = "visual_authority"
    IMAGE_AUTHORITY = "image_authority"


class DocumentSourcePolicy(StrEnum):
    """Document-level source authority after escalation rules."""

    NATIVE_AUTHORITY = "native_authority"
    EMBEDDED_OCR_AUTHORITY = "embedded_ocr_authority"
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
    """Visual agreement status across Phase 3 and Phase 4.5."""

    NOT_EVALUATED_PHASE_3 = "not_evaluated_phase_3"
    EVALUATED_PHASE_4_VISIBILITY = "evaluated_phase_4_visibility"
    EVALUATED_PHASE_45_EMBEDDED_VISUAL = "evaluated_phase_45_embedded_visual"
    EVALUATED_PHASE_45_EMBEDDED_RECOGNITION = "evaluated_phase_45_embedded_recognition"
    EVALUATED_PHASE_45_TARGETED_REPAIR = "evaluated_phase_45_targeted_repair"


class RecognitionMethod(StrEnum):
    """How accepted native text was obtained."""

    NATIVE_PDF = "native_pdf"
    CANONICAL_PDF_NATIVE = "canonical_pdf_native"


class RecognitionStatus(StrEnum):
    """Recognition status for native words (accepted output vs verification-only)."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"


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
    """One native word with canonical geometry.

    Accepted pages use ``recognition_status=accepted`` in ``words``.
    Diagnostic verification candidates use ``recognition_status=rejected`` in
    ``verification_words`` only — never as accepted extraction output.
    """

    id: str = Field(description="Deterministic word id, e.g. word_p0001_000001.")
    page_number: int = Field(ge=1, description="1-based page number.")
    sequence_index: int = Field(ge=0, description="Provisional extraction sequence index.")
    text: str = Field(min_length=1, description="Word text as extracted.")
    normalised_text: str = Field(min_length=1, description="NFC-normalised word text.")
    character_ids: list[str] = Field(description="Linked character ids when available.")
    geometry: Geometry = Field(description="Canonical normalised geometry.")
    pdf_point_bbox: PdfPointBox = Field(description="Top-left PDF-point box.")
    font_names: list[str] = Field(default_factory=list, description="Distinct font names.")
    font_sizes: list[float] = Field(default_factory=list, description="Distinct font sizes.")
    upright: bool = Field(description="Whether linked characters are upright.")
    recognition_method: RecognitionMethod = Field(description="Native recognition method.")
    source_mode: SourceMode = Field(
        description="native_authority for digital-native words; may remain "
        "native_authority on verification candidates pending Phase 4.5 checks."
    )
    recognition_status: RecognitionStatus = Field(
        description="accepted for public words; rejected for verification_words."
    )


class NativeTrustComponents(ApiModel):
    """Component scores in [0, 1] contributing to the native trust score."""

    character_validity_score: float = Field(ge=0.0, le=1.0)
    geometry_validity_score: float = Field(ge=0.0, le=1.0)
    duplication_quality_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Quality after duplicate penalties (1.0 = no duplication pressure). "
            "Formerly named duplication_score; higher means less duplication."
        ),
    )
    token_structure_score: float = Field(ge=0.0, le=1.0)
    text_density_score: float = Field(ge=0.0, le=1.0)
    order_plausibility_score: float = Field(ge=0.0, le=1.0)
    image_compatibility_score: float = Field(ge=0.0, le=1.0)


class DuplicateRuleRecord(ApiModel):
    """One evaluated duplicate-layer rule with visible threshold evidence."""

    rule_id: str
    metric_name: str
    actual_value: float | int | bool | str
    operator: str
    threshold: float | int | bool | str
    mandatory: bool
    passed: bool
    applies_to_path: Literal["A", "B", "both", "info"]
    explanation: str = ""


class DuplicateLayerEvidence(ApiModel):
    """Canonical duplicate-layer decision evidence (single source of truth)."""

    policy_version: str = Field(default=DUPLICATE_LAYER_POLICY_VERSION)
    strict_duplicate_ratio: float = Field(ge=0.0, le=1.0)
    near_overprint_duplicate_ratio: float = Field(ge=0.0, le=1.0)
    duplicate_layer_coverage_ratio: float = Field(ge=0.0, le=1.0)
    matched_near_duplicate_count: int = Field(ge=0)
    duplicate_line_count: int = Field(ge=0)
    duplicate_region_count: int = Field(ge=0)
    dominant_offset_x: float = 0.0
    dominant_offset_y: float = 0.0
    dominant_offset_support_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
    top_k_offset_cluster_support_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
    offset_cluster_count: int = Field(ge=0, default=0)
    geometric_overlap_present: bool = False
    path_a_rules: list[DuplicateRuleRecord] = Field(default_factory=list)
    path_b_rules: list[DuplicateRuleRecord] = Field(default_factory=list)
    path_a_satisfied: bool = False
    path_b_satisfied: bool = False
    selected_path: Literal["A", "B", "none"] = "none"
    hard_rejection: bool = False

    @model_validator(mode="after")
    def _enforce_path_invariants(self) -> DuplicateLayerEvidence:
        if self.selected_path == "A" and not self.path_a_satisfied:
            raise ValueError("selected_path=A requires path_a_satisfied")
        if self.selected_path == "B" and not self.path_b_satisfied:
            raise ValueError("selected_path=B requires path_b_satisfied")
        if self.path_a_satisfied:
            for rule in self.path_a_rules:
                if rule.mandatory and not rule.passed:
                    raise ValueError(f"path_a_satisfied with failed mandatory rule {rule.rule_id}")
        if self.path_b_satisfied:
            for rule in self.path_b_rules:
                if rule.mandatory and not rule.passed:
                    raise ValueError(f"path_b_satisfied with failed mandatory rule {rule.rule_id}")
        if self.hard_rejection and self.selected_path == "none":
            raise ValueError("duplicate hard_rejection requires selected_path A or B")
        if self.selected_path == "none" and self.hard_rejection:
            raise ValueError("selected_path=none forbids duplicate hard_rejection")
        if self.hard_rejection != (self.selected_path in {"A", "B"}):
            raise ValueError("hard_rejection must match selected_path A/B")
        return self


class NativePageMetrics(ApiModel):
    """Safe page-level native quality metrics (no extracted text)."""

    raw_character_count: int = Field(ge=0)
    deduplicated_character_count: int = Field(ge=0)
    word_count: int = Field(ge=0)
    character_count: int = Field(ge=0)
    duplicate_character_ratio: float = Field(ge=0.0, le=1.0)
    strict_duplicate_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ratio removed by strict pdfplumber dedupe (fontname+size).",
    )
    near_overprint_duplicate_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Redundant overprint characters / total characters.",
    )
    duplicate_layer_count: int = Field(
        default=1,
        ge=1,
        description="Estimated distinct near-overprint text layers.",
    )
    dominant_duplicate_offset_x: float = Field(
        default=0.0,
        description="Dominant near-overprint offset X in PDF points.",
    )
    dominant_duplicate_offset_y: float = Field(
        default=0.0,
        description="Dominant near-overprint offset Y in PDF points.",
    )
    duplicate_layer_coverage_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Matched chars in smaller layer / smaller layer size.",
    )
    matched_near_duplicate_count: int = Field(
        default=0,
        ge=0,
        description="Number of near-duplicate glyph matches.",
    )
    dominant_offset_support_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Matches supporting the dominant offset / all matches.",
    )
    matched_word_span: int = Field(
        default=0,
        ge=0,
        description="Approximate distinct word clusters among near-duplicate matches.",
    )
    matched_line_span: int = Field(
        default=0,
        ge=0,
        description="Approximate distinct line bins among near-duplicate matches.",
    )
    top_offset_cluster_support_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Support ratio of the largest tolerant offset cluster.",
    )
    top_k_offset_cluster_support_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Combined support of the top-K tolerant offset clusters.",
    )
    offset_cluster_count: int = Field(
        default=0,
        ge=0,
        description="Number of tolerant displacement clusters among matches.",
    )
    duplicate_line_count: int = Field(
        default=0,
        ge=0,
        description="Lines with severe near-overprint duplication.",
    )
    duplicate_region_count: int = Field(
        default=0,
        ge=0,
        description="Contiguous regions of severely duplicated lines.",
    )
    page_vertical_span_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Vertical span of matched duplicates / page height.",
    )
    page_horizontal_span_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Horizontal span of matched duplicates / page width.",
    )
    hard_rule_path: str = Field(
        default="none",
        description="Near-overprint hard path that fired: none, A, or B.",
    )
    hard_rule_explanation: list[str] = Field(
        default_factory=list,
        description="Dev-oriented hard-rule condition lines derived from DuplicateLayerEvidence.",
    )
    duplicate_layer_evidence: DuplicateLayerEvidence | None = Field(
        default=None,
        description="Canonical duplicate-layer decision evidence (single source of truth).",
    )
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
    hard_rejection: bool = Field(
        description="Overall native hard rejection (any hard rule, including non-duplicate)."
    )
    duplicate_hard_rejection: bool = Field(
        default=False,
        description="True only when a duplicate-layer path (A or B) caused hard rejection.",
    )
    reason_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    metrics: NativePageMetrics
    visual_agreement_status: VisualAgreementStatus = VisualAgreementStatus.NOT_EVALUATED_PHASE_3
    visual_agreement_score: float | None = Field(default=None)
    native_result_available: bool
    visual_processing_required: bool
    quarantined_glyph_count: int = Field(default=0, ge=0)
    quarantined_region_count: int = Field(default=0, ge=0)
    glyph_materiality: str | None = Field(
        default=None,
        description="none | non_material | material | widespread",
    )


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
    verification_words: list[NativeWord] = Field(
        default_factory=list,
        description=(
            "Diagnostic word boxes retained for Phase 4.5 embedded-OCR verification "
            "when the page is not accepted. recognition_status must be rejected. "
            "Never accepted extraction output or LLM hints. Stripped from default API."
        ),
    )
    warnings: list[NativeWarning] = Field(default_factory=list)
    quarantined_glyph_count: int = Field(default=0, ge=0)
    quarantined_region_count: int = Field(default=0, ge=0)
    glyph_materiality: str | None = None


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
