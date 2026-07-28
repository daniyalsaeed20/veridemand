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
    source_native_word_id: str | None = Field(
        default=None,
        description="Native/verification candidate word id this public word was materialised from.",
    )
