"""Printed OCR line/word contracts (Phase 4).

OCR text is NFC-normalised only. No spelling correction, translation, or LLM.
Handwriting assessment remains ``pending_phase_5``. Reading order is provisional.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from backend.app.contracts.base import ApiModel
from backend.app.contracts.geometry import Geometry, NormalisedBoundingBox, NormalisedPolygon


class OcrRecognitionMethod(StrEnum):
    """How printed OCR text was obtained."""

    PADDLEOCR_PRINTED = "paddleocr_printed"
    EMBEDDED_OCR_VERIFIED = "embedded_ocr_verified"


class OcrSourceMode(StrEnum):
    """Page text authority for Phase 4 OCR results."""

    VISUAL_AUTHORITY = "visual_authority"
    EMBEDDED_OCR_AUTHORITY = "embedded_ocr_authority"
    NATIVE_AUTHORITY = "native_authority"


class HandwritingAssessment(StrEnum):
    """Handwriting is not assessed until Phase 5."""

    PENDING_PHASE_5 = "pending_phase_5"


class OcrRecognitionStatus(StrEnum):
    """Public recognition status for an OCR line or word."""

    ACCEPTED = "accepted"
    LOW_CONFIDENCE = "low_confidence"
    EMPTY = "empty"


class WordGeometrySource(StrEnum):
    """Whether word boxes came from Paddle or were derived."""

    PADDLE_WORD_BOX = "paddle_word_box"
    DERIVED_FROM_LINE_POLYGON = "derived_from_line_polygon"
    EMBEDDED_NATIVE_BOX = "embedded_native_box"


class WordScoreSource(StrEnum):
    """Origin of the word recognition score."""

    PADDLE_RECOGNITION = "paddle_recognition"
    INHERITED_FROM_LINE = "inherited_from_line"
    EMBEDDED_VERIFICATION = "embedded_verification"


class PreprocessingVariant(StrEnum):
    """Conservative preprocessing variants used before OCR."""

    ORIGINAL_RGB = "original_rgb"
    GRAYSCALE_AUTOCONTRAST = "grayscale_autocontrast"
    GRAYSCALE = "grayscale"
    CONTRAST_NORMALISED = "contrast_normalised"


class PageProcessingProfile(StrEnum):
    """Cheap visual/structural processing profile (not semantic form ID)."""

    ORDINARY_DOCUMENT = "ordinary_document"
    DENSE_FORM = "dense_form"
    TABLE_LIKE = "table_like"
    SPARSE_DOCUMENT = "sparse_document"
    PHOTO_WITH_TEXT = "photo_with_text"


class OcrQualityStatus(StrEnum):
    """Derived OCR quality status for a single pass or selected result.

    Derived from PrintedOcrQualityEvidence — never from mean confidence alone.
    """

    GOOD = "good"
    USABLE_WITH_WARNINGS = "usable_with_warnings"
    LOW_QUALITY = "low_quality"
    INSUFFICIENT = "insufficient"
    FAILED = "failed"


class OcrPassKind(StrEnum):
    """Which detector-side OCR pass produced a result."""

    PRIMARY = "primary"
    FALLBACK = "fallback"


class ProvisionalItemClass(StrEnum):
    """Provisional classification of an OCR item (Phase 4; not final HTR)."""

    CREDIBLE_PRINTED_TEXT = "credible_printed_text"
    LOW_CONFIDENCE_TEXT = "low_confidence_text"
    ISOLATED_FORM_NUMBER = "isolated_form_number"
    CHECKBOX_OR_SYMBOL_CANDIDATE = "checkbox_or_symbol_candidate"
    LINE_OR_GRID_ARTEFACT = "line_or_grid_artefact"
    HANDWRITING_CANDIDATE_PENDING_PHASE_5 = "handwriting_candidate_pending_phase_5"
    UNRESOLVED = "unresolved"


QUALITY_POLICY_VERSION = "phase4-ocr-quality-v1"


class PixelBoundingBox(ApiModel):
    """Axis-aligned box in rendered pixel space (top-left origin)."""

    x: float = Field(ge=0.0)
    y: float = Field(ge=0.0)
    width: float = Field(gt=0.0)
    height: float = Field(gt=0.0)

    @field_validator("x", "y", "width", "height")
    @classmethod
    def _finite(cls, value: float) -> float:
        import math

        if math.isnan(value) or math.isinf(value):
            raise ValueError("Pixel box values must be finite.")
        return value


class PixelPolygon(ApiModel):
    """Polygon in rendered pixel space."""

    points: list[tuple[float, float]] = Field(min_length=3, max_length=64)

    @field_validator("points")
    @classmethod
    def _finite_points(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        import math

        for x, y in value:
            if math.isnan(x) or math.isinf(x) or math.isnan(y) or math.isinf(y):
                raise ValueError("Pixel polygon points must be finite.")
        return value


class PrintedOcrLine(ApiModel):
    """One printed OCR text line with geometry and confidence."""

    id: str = Field(description="Deterministic id, e.g. ocrline_p0001_000001.")
    page_number: int = Field(ge=1)
    sequence_index: int = Field(ge=0)
    text: str = Field(min_length=1, description="Exact OCR string (NFC applied separately).")
    normalised_text: str = Field(min_length=1, description="NFC-normalised OCR text.")
    detection_score: Annotated[float, Field(ge=0.0, le=1.0)]
    recognition_score: Annotated[float, Field(ge=0.0, le=1.0)]
    recognition_status: OcrRecognitionStatus
    polygon: NormalisedPolygon
    bbox: NormalisedBoundingBox
    geometry: Geometry | None = Field(default=None, description="Combined normalised geometry.")
    pixel_polygon: PixelPolygon
    pixel_bbox: PixelBoundingBox
    preprocessing_variant: PreprocessingVariant
    recognition_method: OcrRecognitionMethod = OcrRecognitionMethod.PADDLEOCR_PRINTED
    source_mode: OcrSourceMode = OcrSourceMode.VISUAL_AUTHORITY
    handwriting_assessment: HandwritingAssessment = HandwritingAssessment.PENDING_PHASE_5
    ocr_pass: OcrPassKind | None = Field(
        default=None,
        description="Detector-side pass that produced this line (primary or fallback).",
    )
    provisional_class: ProvisionalItemClass | None = Field(
        default=None,
        description="Provisional noise/text classification for transcript filtering.",
    )
    source_native_word_ids: list[str] = Field(
        default_factory=list,
        description="Native/verification candidate word ids that produced this line.",
    )


class PrintedOcrWord(ApiModel):
    """One printed OCR word/token with geometry and confidence."""

    id: str = Field(description="Deterministic id, e.g. ocrword_p0001_000001.")
    page_number: int = Field(ge=1)
    line_id: str
    sequence_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    normalised_text: str = Field(min_length=1)
    recognition_score: Annotated[float, Field(ge=0.0, le=1.0)]
    score_source: WordScoreSource
    polygon: NormalisedPolygon
    bbox: NormalisedBoundingBox
    geometry: Geometry | None = None
    pixel_polygon: PixelPolygon
    pixel_bbox: PixelBoundingBox
    geometry_source: WordGeometrySource
    geometry_precision: str = Field(
        default="detector",
        description="detector when paddle_word_box; approximate when derived.",
    )
    recognition_method: OcrRecognitionMethod = OcrRecognitionMethod.PADDLEOCR_PRINTED
    recognition_status: OcrRecognitionStatus
    handwriting_assessment: HandwritingAssessment = HandwritingAssessment.PENDING_PHASE_5
    source_mode: OcrSourceMode = OcrSourceMode.VISUAL_AUTHORITY
    ocr_pass: OcrPassKind | None = Field(
        default=None,
        description="Detector-side pass that produced this word (primary or fallback).",
    )
    provisional_class: ProvisionalItemClass | None = Field(
        default=None,
        description="Provisional noise/text classification for transcript filtering.",
    )
    source_native_word_id: str | None = Field(
        default=None,
        description="Native/verification candidate word id this public word was materialised from.",
    )


class ProvisionalItemCounts(ApiModel):
    """Counts of provisional OCR item classes (no text)."""

    credible_text: int = Field(default=0, ge=0)
    low_confidence: int = Field(default=0, ge=0)
    isolated_form_numbers: int = Field(default=0, ge=0)
    symbol_candidates: int = Field(default=0, ge=0)
    artefacts: int = Field(default=0, ge=0)
    unresolved: int = Field(default=0, ge=0)
    handwriting_pending: int = Field(default=0, ge=0)


class PrintedOcrQualityEvidence(ApiModel):
    """Canonical typed evidence for printed OCR quality decisions.

    Score directions (documented so high never means both good and bad):

    - fragmentation_score: higher = more suspected fragmentation (worse)
    - over_segmentation_score: higher = more suspected over-segmentation (worse)
    - box_overlap_ratio: higher = more overlapping OCR boxes (worse)
    - near_duplicate_box_ratio: higher = more near-duplicate boxes (worse)
    - grid_intersection_ratio: higher = more boxes intersecting ruling lines (signal)
    - text_coverage_ratio: higher = more page area covered by OCR geometry (better)
    - geometry_valid_ratio: higher = better
    - out_of_bounds_ratio: higher = worse
    - low_confidence_ratio: higher = worse
    - single_character_* / symbol_only_* / numeric_fragment_ratio: higher = worse noise
    - mean_confidence / median_confidence: recognition confidence aggregates only;
      never treated as transcript accuracy.
    """

    policy_version: str = Field(default=QUALITY_POLICY_VERSION)
    page_number: int = Field(ge=1)
    route: str | None = None
    ocr_pass: OcrPassKind
    detector_limit_side: int = Field(gt=0)
    preprocessing_variant: PreprocessingVariant | None = None
    page_profile: PageProcessingProfile = PageProcessingProfile.ORDINARY_DOCUMENT
    profile_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    profile_reason_codes: list[str] = Field(default_factory=list)

    detected_region_count: int = Field(default=0, ge=0)
    line_count: int = Field(default=0, ge=0)
    word_count: int = Field(default=0, ge=0)

    mean_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    median_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    p10_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    low_confidence_ratio: float = Field(default=0.0, ge=0.0, le=1.0)

    single_character_token_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    single_character_line_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    symbol_only_token_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    symbol_only_line_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    numeric_fragment_ratio: float = Field(default=0.0, ge=0.0, le=1.0)

    median_token_length: float = Field(default=0.0, ge=0.0)
    median_words_per_line: float = Field(default=0.0, ge=0.0)

    fragmentation_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Higher means more suspected fragmentation.",
    )
    over_segmentation_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Higher means more suspected over-segmentation.",
    )
    box_overlap_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    near_duplicate_box_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    grid_intersection_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    text_coverage_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Higher means more page area represented by OCR geometry.",
    )
    geometry_valid_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Higher means better geometry validity.",
    )
    out_of_bounds_ratio: float = Field(default=0.0, ge=0.0, le=1.0)

    fallback_recommended: bool = False
    fallback_reason_codes: list[str] = Field(default_factory=list)
    quality_gate_passed: bool = True
    quality_status: OcrQualityStatus = OcrQualityStatus.GOOD


class ConfidenceDistribution(ApiModel):
    """Privacy-safe recognition confidence distribution (no text)."""

    mean: float | None = Field(default=None, ge=0.0, le=1.0)
    median: float | None = Field(default=None, ge=0.0, le=1.0)
    p10: float | None = Field(default=None, ge=0.0, le=1.0)
    low_confidence_ratio: float = Field(default=0.0, ge=0.0, le=1.0)


class OcrPassComparison(ApiModel):
    """Typed comparison of primary vs fallback OCR passes."""

    primary_quality: PrintedOcrQualityEvidence
    fallback_quality: PrintedOcrQualityEvidence | None = None
    primary_valid_words: int = Field(default=0, ge=0)
    fallback_valid_words: int = Field(default=0, ge=0)
    primary_confidence_distribution: ConfidenceDistribution
    fallback_confidence_distribution: ConfidenceDistribution | None = None
    primary_fragmentation: float = Field(default=0.0, ge=0.0, le=1.0)
    fallback_fragmentation: float | None = Field(default=None, ge=0.0, le=1.0)
    primary_geometry_quality: float = Field(default=1.0, ge=0.0, le=1.0)
    fallback_geometry_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    primary_text_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    fallback_text_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    selected_pass: OcrPassKind
    selection_reason_codes: list[str] = Field(default_factory=list)
