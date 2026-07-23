"""Visual page processing contracts (Phase 4).

Printed OCR results are intermediate. Final structured extraction, handwriting
routing, and vision-LLM transcription remain later phases.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import NormalisedBoundingBox, NormalisedPolygon
from backend.app.contracts.identifiers import DocumentId
from backend.app.contracts.native import DocumentSourcePolicy, SourceMode
from backend.app.contracts.ocr import (
    HandwritingAssessment,
    PreprocessingVariant,
    PrintedOcrLine,
    PrintedOcrWord,
)


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
    """Visual agreement status after Phase 4 visibility probing."""

    NOT_EVALUATED_PHASE_3 = "not_evaluated_phase_3"
    EVALUATED_PHASE_4_VISIBILITY = "evaluated_phase_4_visibility"


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
    render_dpi: float | None = Field(default=None, gt=0)
    render_width_pixels: int | None = Field(default=None, ge=0)
    render_height_pixels: int | None = Field(default=None, ge=0)
    preprocessing_variant: PreprocessingVariant | None = None
    fallback_used: bool = False
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
    visual_result_available: bool = False
    visual_processing_attempted: bool = False
    handwriting_assessment: HandwritingAssessment = HandwritingAssessment.PENDING_PHASE_5
    warnings: list[VisualWarning] = Field(default_factory=list)
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


class VisualPageSummary(ApiModel):
    """Compact per-page row for document visual summaries."""

    page_number: int = Field(ge=1)
    status: VisualPageStatus
    source_mode: SourceMode
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
    pages_selected: int = Field(ge=0)
    pages_completed: int = Field(ge=0)
    pages_no_text: int = Field(ge=0)
    pages_failed: int = Field(ge=0)
    pages_cancelled: int = Field(ge=0)
    native_pages_retained: int = Field(ge=0)
    native_pages_downgraded: int = Field(ge=0)
    visual_result_available: bool = False
    handwriting_assessment_pending: bool = True
    final_result_available: bool = False
    canonical_document_available: bool = False
    document_source_policy: DocumentSourcePolicy | None = None
    progress: VisualProgress
    model_info: VisualModelInfo | None = None
    page_summaries: list[VisualPageSummary] = Field(default_factory=list)
    warnings: list[VisualWarning] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None
    user_status_message: str | None = None
    error_codes: list[str] = Field(default_factory=list)
