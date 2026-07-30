"""Visual page processing contracts (Phase 4).

Printed OCR results are intermediate. Final structured extraction, handwriting
routing, and vision-LLM transcription remain later phases.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, model_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPolygon
from backend.app.contracts.identifiers import DocumentId
from backend.app.contracts.native import DocumentSourcePolicy, SourceMode
from backend.app.contracts.ocr import (
    HandwritingAssessment,
    HandwritingClassificationEvidence,
    OcrPassComparison,
    OcrPassKind,
    OcrQualityStatus,
    PageProcessingProfile,
    PreprocessingVariant,
    PrintedOcrLine,
    PrintedOcrQualityEvidence,
    PrintedOcrWord,
    ProvisionalItemCounts,
)
from backend.app.contracts.routing import FinalRouteHistogram


class VisualPageStatus(StrEnum):
    """Lifecycle of visual/OCR processing for one page."""

    PENDING = "pending"
    RENDERING = "rendering"
    DETECTING = "detecting"
    RECOGNISING = "recognising"
    GROUPING = "grouping"
    COMPLETED = "completed"
    COMPLETED_NO_TEXT = "completed_no_text"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED_NATIVE_RETAINED = "skipped_native_retained"
    SKIPPED_EMBEDDED_OCR_VERIFIED = "skipped_embedded_ocr_verified"
    TARGETED_REPAIR_COMPLETED = "targeted_repair_completed"


class VisualProcessingStatus(StrEnum):
    """Document-level visual processing lifecycle."""

    VISUAL_PENDING = "visual_pending"
    VISUAL_PROCESSING = "visual_processing"
    VISUAL_PROCESSING_COMPLETE = "visual_processing_complete"
    VISUAL_PROCESSING_PARTIAL = "visual_processing_partial"
    VISUAL_PROCESSING_FAILED = "visual_processing_failed"
    CANCELLED = "cancelled"
    NOT_REQUIRED = "not_required"


class NativeVisibilityDecision(StrEnum):
    """Outcome of the Phase 4 native-text visibility probe."""

    NATIVE_TEXT_VISUALLY_SUPPORTED = "native_text_visually_supported"
    NATIVE_TEXT_NOT_VISUALLY_PRESENT = "native_text_not_visually_present"
    NATIVE_TEXT_VISIBILITY_UNCERTAIN = "native_text_visibility_uncertain"
    NOT_EVALUATED = "not_evaluated"
    INSUFFICIENT_WORDS = "insufficient_words"


class VisualAgreementStatusPhase4(StrEnum):
    """Visual agreement status after Phase 4 / 4.5 probing."""

    NOT_EVALUATED_PHASE_3 = "not_evaluated_phase_3"
    EVALUATED_PHASE_4_VISIBILITY = "evaluated_phase_4_visibility"
    EVALUATED_PHASE_45_EMBEDDED_VISUAL = "evaluated_phase_45_embedded_visual"
    EVALUATED_PHASE_45_EMBEDDED_RECOGNITION = "evaluated_phase_45_embedded_recognition"
    EVALUATED_PHASE_45_TARGETED_REPAIR = "evaluated_phase_45_targeted_repair"


class PageResultState(StrEnum):
    """Canonical terminal page-result state (Phase 4 reconciled authority)."""

    DIGITAL_NATIVE = "digital_native"
    EMBEDDED_OCR_VERIFIED = "embedded_ocr_verified"
    EMBEDDED_OCR_TARGETED_REPAIR = "embedded_ocr_targeted_repair"
    FULL_VISUAL_OCR = "full_visual_ocr"
    VISUAL_NO_TEXT = "visual_no_text"
    PAGE_FAILED = "page_failed"
    PENDING = "pending"
    CANCELLED = "cancelled"


class AgreementEvaluationStatus(StrEnum):
    """Simplified agreement outcome for Phase 4 embedded verification UI."""

    NOT_EVALUATED = "not_evaluated"
    PASSED = "passed"
    FAILED = "failed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_REQUIRED = "not_required"


class OverlaySourceKind(StrEnum):
    """Provenance tag for overlay boxes in the canonical viewer."""

    NATIVE_PDF_WORD = "native_pdf_word"
    VERIFIED_EMBEDDED_OCR_WORD = "verified_embedded_ocr_word"
    VERIFIED_EMBEDDED_OCR_LINE = "verified_embedded_ocr_line"
    TARGETED_REPAIR_WORD = "targeted_repair_word"
    PRINTED_VISUAL_OCR_WORD = "printed_visual_ocr_word"
    PRINTED_VISUAL_OCR_LINE = "printed_visual_ocr_line"


# Exact user-facing source labels keyed by PageResultState.
PAGE_RESULT_SOURCE_LABELS: dict[PageResultState, str] = {
    PageResultState.DIGITAL_NATIVE: "Native PDF text",
    PageResultState.EMBEDDED_OCR_VERIFIED: "Verified embedded OCR",
    PageResultState.EMBEDDED_OCR_TARGETED_REPAIR: "Verified embedded OCR with visual repair",
    PageResultState.FULL_VISUAL_OCR: "Printed visual OCR",
    PageResultState.VISUAL_NO_TEXT: "No meaningful text detected",
    PageResultState.PAGE_FAILED: "Page processing failed",
    PageResultState.PENDING: "Processing",
    PageResultState.CANCELLED: "Cancelled",
}


def source_label_for_page_result_state(state: PageResultState | str | None) -> str:
    """Return the canonical source label for a page-result state."""

    if state is None:
        return "Processing"
    try:
        key = state if isinstance(state, PageResultState) else PageResultState(str(state))
    except ValueError:
        return "Processing"
    return PAGE_RESULT_SOURCE_LABELS[key]


class ReadingOrderStatus(StrEnum):
    """Reading order is provisional in Phase 4."""

    PROVISIONAL_PHASE_4 = "provisional_phase_4"


class ReadingOrderMethod(StrEnum):
    """How provisional reading order was produced."""

    GEOMETRIC_COLUMNS_PHASE_4 = "geometric_columns_phase_4"


class VisualBlockType(StrEnum):
    """Block type — semantic labels are deferred."""

    TEXT_UNKNOWN = "text_unknown"


class NativeVisibilityResult(ApiModel):
    """Safe visibility-probe diagnostics (no native or OCR text)."""

    visual_agreement_status: VisualAgreementStatusPhase4
    native_visibility_score: float | None = Field(default=None, ge=0.0, le=1.0)
    native_visible_word_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    native_blank_like_word_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    sampled_word_count: int = Field(default=0, ge=0)
    native_visibility_decision: NativeVisibilityDecision
    reason_codes: list[str] = Field(default_factory=list)
    downgraded: bool = False


class VisualReadingOrder(ApiModel):
    """Provisional page-local reading order."""

    order_method: ReadingOrderMethod = ReadingOrderMethod.GEOMETRIC_COLUMNS_PHASE_4
    order_status: ReadingOrderStatus = ReadingOrderStatus.PROVISIONAL_PHASE_4
    line_ids: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)
    diagnostic_ocr_sequence_line_ids: list[str] = Field(
        default_factory=list,
        description="Original OCR detection sequence (diagnostic only).",
    )


class VisualTextBlock(ApiModel):
    """Geometrically grouped OCR lines (no semantic table/header labels)."""

    id: str = Field(description="Deterministic id, e.g. ocrblock_p0001_000001.")
    page_number: int = Field(ge=1)
    sequence_index: int = Field(ge=0)
    line_ids: list[str] = Field(min_length=1)
    polygon: NormalisedPolygon
    bbox: NormalisedBoundingBox
    block_type: VisualBlockType = VisualBlockType.TEXT_UNKNOWN
    reading_order_index: int = Field(ge=0)
    reading_order_status: ReadingOrderStatus = ReadingOrderStatus.PROVISIONAL_PHASE_4


class VisualWarning(ApiModel):
    """Safe visual/OCR warning without text payloads."""

    code: str
    message: str
    page_number: int | None = Field(default=None, ge=1)


class VisualModelInfo(ApiModel):
    """Model identifiers exposed in summaries (no filesystem paths)."""

    detection_model_name: str
    recognition_model_name: str
    paddleocr_version: str | None = None
    paddlepaddle_version: str | None = None
    pypdfium2_version: str | None = None
    device: str = "cpu"
    engine: str = "paddle_static"
    model_tree_hash: str | None = None


class VisualProgress(ApiModel):
    """Monotonic visual-stage progress (capped at Phase 4 maximum of 65)."""

    percent: Annotated[int, Field(ge=0, le=65)]
    pages_completed: int = Field(ge=0)
    pages_total: int = Field(ge=0)
    current_page: int | None = Field(default=None, ge=1)
    current_page_stage: str | None = None


class VisualPageResult(ApiModel):
    """Published per-page visual/OCR result."""

    page_number: int = Field(ge=1)
    status: VisualPageStatus
    source_mode: SourceMode
    page_result_state: PageResultState | None = Field(
        default=None,
        description="Canonical terminal page-result state after Phase 4 reconciliation.",
    )
    source_label: str | None = Field(
        default=None,
        description="Exact user-facing source label for this page result.",
    )
    render_dpi: float | None = Field(default=None, gt=0)
    render_width_pixels: int | None = Field(default=None, ge=0)
    render_height_pixels: int | None = Field(default=None, ge=0)
    preprocessing_variant: PreprocessingVariant | None = None
    fallback_used: bool = False
    selected_ocr_pass: OcrPassKind | None = None
    primary_quality_status: OcrQualityStatus | None = None
    fallback_quality_status: OcrQualityStatus | None = None
    fallback_reason_codes: list[str] = Field(default_factory=list)
    quality_policy_version: str | None = None
    page_profile: PageProcessingProfile | None = None
    page_profile_reason_codes: list[str] = Field(default_factory=list)
    primary_quality: PrintedOcrQualityEvidence | None = None
    fallback_quality: PrintedOcrQualityEvidence | None = None
    ocr_pass_comparison: OcrPassComparison | None = None
    provisional_item_counts: ProvisionalItemCounts | None = None
    primary_limit_side: int | None = Field(default=None, gt=0)
    fallback_limit_side: int | None = Field(default=None, gt=0)
    fallback_duration_ms: int | None = Field(default=None, ge=0)
    line_count: int = Field(default=0, ge=0)
    word_count: int = Field(default=0, ge=0)
    average_detection_score: float | None = Field(default=None, ge=0.0, le=1.0)
    average_recognition_score: float | None = Field(default=None, ge=0.0, le=1.0)
    low_confidence_line_count: int = Field(default=0, ge=0)
    lines: list[PrintedOcrLine] = Field(default_factory=list)
    words: list[PrintedOcrWord] = Field(default_factory=list)
    blocks: list[VisualTextBlock] = Field(default_factory=list)
    reading_order: VisualReadingOrder | None = None
    native_visibility_result: NativeVisibilityResult | None = None
    page_route: str | None = Field(
        default=None, description="Phase 4.5 page route when hybrid routing is enabled."
    )
    route_reason_codes: list[str] = Field(default_factory=list)
    visual_agreement_status: AgreementEvaluationStatus = AgreementEvaluationStatus.NOT_EVALUATED
    visual_agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)
    visual_agreement_policy_version: str | None = None
    recognition_agreement_status: AgreementEvaluationStatus = (
        AgreementEvaluationStatus.NOT_EVALUATED
    )
    recognition_agreement_score: float | None = Field(default=None, ge=0.0, le=1.0)
    recognition_sample_count: int = Field(default=0, ge=0)
    overlay_source: OverlaySourceKind | None = None
    visual_result_available: bool = False
    visual_processing_attempted: bool = False
    no_text_reason_code: str | None = None
    handwriting_assessment: HandwritingAssessment = HandwritingAssessment.PENDING_PHASE_5
    handwriting_classification: HandwritingClassificationEvidence | None = Field(
        default=None,
        description=(
            "Phase 5 page-level classification evidence. Optional until Task 4; "
            "Phase 4 stamp sites leave this unset."
        ),
    )
    warnings: list[VisualWarning] = Field(default_factory=list)
    quarantined_glyph_count: int = Field(default=0, ge=0)
    quarantined_region_count: int = Field(default=0, ge=0)
    glyph_materiality: str | None = None
    phase3_page_decision: str | None = None
    document_escalation_applied: bool = False
    page_restored_after_escalation: bool = False
    # Targeted-repair aggregates (privacy-safe counts only).
    retained_native_words: int | None = Field(default=None, ge=0)
    retained_embedded_words: int | None = Field(default=None, ge=0)
    repaired_words: int | None = Field(default=None, ge=0)
    suppressed_words: int | None = Field(default=None, ge=0)
    repair_region_count: int | None = Field(default=None, ge=0)
    repair_quality_status: str | None = None
    repair_method: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    peak_rss_mb: float | None = Field(default=None, ge=0.0)
    # Privacy-safe performance observability (no OCR text).
    render_duration_seconds: float | None = Field(default=None, ge=0.0)
    preprocess_duration_seconds: float | None = Field(default=None, ge=0.0)
    paddle_pipeline_duration_seconds: float | None = Field(default=None, ge=0.0)
    adapt_duration_seconds: float | None = Field(default=None, ge=0.0)
    mapping_duration_seconds: float | None = Field(default=None, ge=0.0)
    grouping_duration_seconds: float | None = Field(default=None, ge=0.0)
    source_width_px: int | None = Field(default=None, ge=0)
    source_height_px: int | None = Field(default=None, ge=0)
    detector_input_width: int | None = Field(default=None, ge=0)
    detector_input_height: int | None = Field(default=None, ge=0)
    requested_dpi: float | None = Field(default=None, gt=0)
    render_source_policy: str | None = None
    detection_model_name: str | None = None
    recognition_model_name: str | None = None
    cpu_threads: int | None = Field(default=None, ge=0)
    error_code: str | None = None

    @model_validator(mode="after")
    def _enforce_page_result_invariants(self) -> VisualPageResult:
        state = self.page_result_state
        if state is None and self.page_route:
            try:
                state = PageResultState(self.page_route)
            except ValueError:
                state = None

        if self.source_label is None and state is not None:
            object.__setattr__(self, "source_label", source_label_for_page_result_state(state))

        if state is PageResultState.EMBEDDED_OCR_VERIFIED:
            if self.source_mode is not SourceMode.EMBEDDED_OCR_AUTHORITY:
                raise ValueError(
                    "embedded_ocr_verified requires source_mode=embedded_ocr_authority."
                )
            if self.visual_agreement_status is AgreementEvaluationStatus.NOT_EVALUATED:
                raise ValueError(
                    "embedded_ocr_authority requires completed visual agreement evaluation."
                )
            if self.visual_agreement_status is not AgreementEvaluationStatus.PASSED:
                raise ValueError("embedded_ocr_authority requires visual_agreement_status=passed.")
            if not self.visual_result_available:
                raise ValueError(
                    "embedded_ocr_verified requires visual_result_available=true with "
                    "materialised verified output."
                )
            if self.word_count < 1 and self.line_count < 1:
                raise ValueError(
                    "embedded_ocr_verified requires at least one verified public word or line."
                )
            if len(self.words) < 1 and len(self.lines) < 1:
                raise ValueError(
                    "embedded_ocr_verified requires materialised words or lines in the result."
                )
            expected = source_label_for_page_result_state(PageResultState.EMBEDDED_OCR_VERIFIED)
            if self.source_label != expected:
                raise ValueError(
                    f"embedded_ocr_verified source_label must be {expected!r}, "
                    f"got {self.source_label!r}."
                )

        if state is PageResultState.EMBEDDED_OCR_TARGETED_REPAIR:
            if self.source_mode is not SourceMode.EMBEDDED_OCR_AUTHORITY:
                raise ValueError(
                    "embedded_ocr_targeted_repair requires source_mode=embedded_ocr_authority."
                )
            if not self.visual_result_available or (self.word_count < 1 and self.line_count < 1):
                raise ValueError(
                    "embedded_ocr_targeted_repair requires materialised verified/repaired output."
                )

        if state is PageResultState.VISUAL_NO_TEXT:
            if self.no_text_reason_code is None:
                raise ValueError("visual_no_text requires a no_text_reason_code.")
            if self.word_count > 0 or self.line_count > 0:
                raise ValueError("visual_no_text must not publish words or lines.")

        if state is PageResultState.PAGE_FAILED:
            if not self.error_code:
                raise ValueError("page_failed requires a typed error_code.")
            if self.source_mode is SourceMode.EMBEDDED_OCR_AUTHORITY:
                raise ValueError("page_failed must not claim embedded_ocr_authority.")

        if (
            self.source_mode is SourceMode.EMBEDDED_OCR_AUTHORITY
            and self.visual_agreement_status is AgreementEvaluationStatus.NOT_EVALUATED
        ):
            raise ValueError(
                "embedded_ocr_authority + visual agreement not evaluated is forbidden."
            )

        if (
            self.source_mode is SourceMode.EMBEDDED_OCR_AUTHORITY
            and self.word_count == 0
            and self.line_count == 0
            and state
            not in {
                PageResultState.PENDING,
                PageResultState.CANCELLED,
                PageResultState.PAGE_FAILED,
            }
        ):
            raise ValueError("embedded_ocr_authority with zero verified words/lines is forbidden.")

        return self


class VisualPageSummary(ApiModel):
    """Compact per-page row for document visual summaries."""

    page_number: int = Field(ge=1)
    status: VisualPageStatus
    source_mode: SourceMode
    page_result_state: PageResultState | None = None
    source_label: str | None = None
    line_count: int = Field(default=0, ge=0)
    word_count: int = Field(default=0, ge=0)
    visual_result_available: bool = False
    native_retained: bool = False
    native_downgraded: bool = False
    average_recognition_score: float | None = Field(default=None, ge=0.0, le=1.0)
    error_code: str | None = None


class VisualDocumentSummary(ApiModel):
    """Public visual-processing summary for a document."""

    document_id: DocumentId
    visual_processing_status: VisualProcessingStatus
    page_count: int = Field(ge=0)
    document_pages_total: int = Field(default=0, ge=0)
    pages_selected: int = Field(ge=0)
    pages_completed: int = Field(ge=0)
    pages_no_text: int = Field(ge=0)
    pages_failed: int = Field(ge=0)
    pages_cancelled: int = Field(ge=0)
    native_pages_retained: int = Field(
        ge=0,
        description=(
            "Diagnostic: pages retained without full visual OCR "
            "(digital-native union embedded-verified). Not exclusive digital_native."
        ),
    )
    native_pages_downgraded: int = Field(ge=0)
    pages_not_requiring_full_ocr: int = Field(default=0, ge=0)
    final_route_histogram: FinalRouteHistogram | None = Field(
        default=None,
        description=(
            "Exclusive terminal page_result_state histogram; "
            "terminal buckets sum to document_pages_total when complete."
        ),
    )
    embedded_ocr_pages_verified: int = Field(default=0, ge=0)
    embedded_pages_verified: int = Field(default=0, ge=0)
    targeted_repair_pages: int = Field(default=0, ge=0)
    full_ocr_pages: int = Field(default=0, ge=0)
    full_ocr_pages_selected: int = Field(default=0, ge=0)
    full_ocr_pages_completed: int = Field(default=0, ge=0)
    no_text_pages: int = Field(default=0, ge=0)
    failed_pages: int = Field(default=0, ge=0)
    visual_no_text_pages: int = Field(default=0, ge=0)
    visual_result_available: bool = False
    handwriting_assessment_pending: bool = True
    final_result_available: bool = False
    canonical_document_available: bool = False
    document_source_policy: DocumentSourcePolicy | None = None
    phase3_provisional_document_policy: DocumentSourcePolicy | None = Field(
        default=None,
        description="Phase 3 provisional document policy retained for diagnostics.",
    )
    progress: VisualProgress
    model_info: VisualModelInfo | None = None
    page_summaries: list[VisualPageSummary] = Field(default_factory=list)
    warnings: list[VisualWarning] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None
    user_status_message: str | None = None
    error_codes: list[str] = Field(default_factory=list)
