"""OCR coordinate conversion and quality assessment unit tests."""

from __future__ import annotations

from app.models.app_settings import AppSettings
from app.models.enums import ExtractionMethod
from app.models.source_token import SourceToken
from app.services.extraction.coordinates import image_polygon_to_normalized
from app.services.extraction.ocr_page import detections_to_tokens
from app.services.extraction.ocr_quality import (
    OcrPageOutcome,
    assess_ocr_tokens,
    score_pass_for_retry_choice,
)
from app.services.ocr.types import OcrDetection, OcrRawResult


def test_image_polygon_normalized_basic() -> None:
    poly = image_polygon_to_normalized(
        [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (0.0, 50.0)],
        image_width=100,
        image_height=100,
    )
    assert poly is not None
    assert poly[0] == [0.0, 0.0]
    assert poly[2] == [1.0, 0.5]


def test_image_polygon_rejects_degenerate() -> None:
    assert (
        image_polygon_to_normalized(
            [(1.0, 1.0), (1.1, 1.0), (1.1, 1.1), (1.0, 1.1)],
            image_width=100,
            image_height=100,
        )
        is None
    )


def test_image_polygon_oob_clamped_or_rejected() -> None:
    poly = image_polygon_to_normalized(
        [(-5.0, 0.0), (50.0, 0.0), (50.0, 20.0), (-5.0, 20.0)],
        image_width=100,
        image_height=100,
        clamp=True,
    )
    # Small OOB can clamp; large drift rejects
    assert poly is None or all(0.0 <= p[0] <= 1.0 and 0.0 <= p[1] <= 1.0 for p in poly)


def test_detections_to_tokens_stable() -> None:
    raw = OcrRawResult(
        detections=[
            OcrDetection(
                text="Claim",
                confidence=0.91,
                polygon_px=[(10, 10), (60, 10), (60, 30), (10, 30)],
            )
        ]
    )
    tokens = detections_to_tokens(
        raw,
        document_id="doc_01JEXAMPLE000000000000001",
        page_number=1,
        image_width=100,
        image_height=100,
    )
    assert len(tokens) == 1
    assert tokens[0].method == ExtractionMethod.OCR
    assert tokens[0].id.startswith("tok_")


def test_quality_blank_and_low_conf() -> None:
    settings = AppSettings()
    blank = assess_ocr_tokens([], settings=settings)
    assert blank.outcome == OcrPageOutcome.BLANK

    low = [
        SourceToken(
            id="tok_01JEXAMPLE000000000000001",
            document_id="doc_01JEXAMPLE000000000000001",
            page_number=1,
            text="x",
            confidence=0.2,
            polygon=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
            method=ExtractionMethod.OCR,
        )
    ]
    assessment = assess_ocr_tokens(low, settings=settings)
    assert assessment.outcome in {
        OcrPageOutcome.LOW_CONFIDENCE,
        OcrPageOutcome.USABLE_WITH_WARNING,
    }


def test_retry_chooses_better_score() -> None:
    settings = AppSettings()
    weak = [
        SourceToken(
            id="tok_01JEXAMPLE000000000000001",
            document_id="doc_01JEXAMPLE000000000000001",
            page_number=1,
            text="a",
            confidence=0.4,
            polygon=[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
            method=ExtractionMethod.OCR,
        )
    ]
    strong = [
        SourceToken(
            id="tok_01JEXAMPLE000000000000002",
            document_id="doc_01JEXAMPLE000000000000001",
            page_number=1,
            text="Invoice Total",
            confidence=0.96,
            polygon=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.2], [0.1, 0.2]],
            method=ExtractionMethod.OCR,
        )
    ]
    assert score_pass_for_retry_choice(strong, settings=settings) > score_pass_for_retry_choice(
        weak, settings=settings
    )
