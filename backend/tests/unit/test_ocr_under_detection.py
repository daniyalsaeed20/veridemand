"""B-03 under-detection quality gate unit tests (synthetic; no PII)."""

from __future__ import annotations

from app.models.app_settings import AppSettings
from app.models.enums import ExtractionMethod
from app.models.source_token import SourceToken
from app.services.extraction.ocr_quality import (
    OcrPageOutcome,
    PageInkContext,
    assess_ocr_tokens,
    score_pass_for_retry_choice,
)
from app.services.extraction.preprocess import invert_polygon_affine


def _tok(
    tid: str,
    *,
    text: str = "x",
    conf: float = 0.95,
    poly: list[list[float]] | None = None,
) -> SourceToken:
    return SourceToken(
        id=tid,
        document_id="doc_01JEXAMPLE000000000000001",
        page_number=1,
        text=text,
        confidence=conf,
        polygon=poly or [[0.01, 0.01], [0.05, 0.01], [0.05, 0.03], [0.01, 0.03]],
        method=ExtractionMethod.OCR,
    )


def test_ink_rich_sparse_tokens_under_detected() -> None:
    settings = AppSettings()
    tokens = [_tok(f"tok_01JEXAMPLE00000000000000{i:02d}", conf=0.93) for i in range(1, 7)]
    ink = PageInkContext(
        dark_pixel_fraction=0.335,
        width=1700,
        height=2200,
        megapixels=3.74,
    )
    assessment = assess_ocr_tokens(tokens, settings=settings, ink=ink)
    assert assessment.under_detection is True
    assert assessment.outcome == OcrPageOutcome.FAILED
    assert "insufficient_coverage" in assessment.quality_flags
    assert assessment.issue_type == "extraction.insufficient_ocr_coverage"


def test_sparse_low_ink_six_tokens_not_under_detected() -> None:
    """Genuinely sparse page: few tokens + low ink must not trip under-detection."""
    settings = AppSettings()
    tokens = [_tok(f"tok_01JEXAMPLE00000000000000{i:02d}") for i in range(1, 7)]
    ink = PageInkContext(
        dark_pixel_fraction=0.02,
        width=800,
        height=1000,
        megapixels=0.8,
    )
    assessment = assess_ocr_tokens(tokens, settings=settings, ink=ink)
    assert assessment.under_detection is False
    assert "insufficient_coverage" not in assessment.quality_flags


def test_dark_pixels_alone_do_not_fail_forms() -> None:
    """Dense form graphics with adequate OCR coverage stay usable."""
    settings = AppSettings()
    # Many tokens covering substantial area
    tokens = []
    for i in range(40):
        y0 = 0.05 + (i % 20) * 0.04
        x0 = 0.05 + (i // 20) * 0.4
        tokens.append(
            _tok(
                f"tok_01JEXAMPLE0000000000000{i:02d}",
                text=f"Field{i}",
                conf=0.92,
                poly=[
                    [x0, y0],
                    [x0 + 0.3, y0],
                    [x0 + 0.3, y0 + 0.03],
                    [x0, y0 + 0.03],
                ],
            )
        )
    ink = PageInkContext(
        dark_pixel_fraction=0.40,
        width=1700,
        height=2200,
        megapixels=3.74,
    )
    assessment = assess_ocr_tokens(tokens, settings=settings, ink=ink)
    assert assessment.under_detection is False
    assert assessment.outcome == OcrPageOutcome.USABLE


def test_retry_score_prefers_coverage_over_confidence() -> None:
    settings = AppSettings()
    sparse = [_tok("tok_01JEXAMPLE000000000000001", conf=0.99)]
    dense = [
        _tok(
            f"tok_01JEXAMPLE0000000000000{i:02d}",
            conf=0.80,
            text=f"Word{i}",
            poly=[
                [0.05, 0.02 + i * 0.03],
                [0.45, 0.02 + i * 0.03],
                [0.45, 0.045 + i * 0.03],
                [0.05, 0.045 + i * 0.03],
            ],
        )
        for i in range(30)
    ]
    ink = PageInkContext(0.3, 1000, 1200, 1.2)
    assert score_pass_for_retry_choice(
        dense, settings=settings, ink=ink
    ) > score_pass_for_retry_choice(sparse, settings=settings, ink=ink)


def test_deskew_inverse_maps_polygon_back() -> None:
    # 90-ish mild rotation affine around origin for unit test
    # Identity forward → inverse is identity
    poly = [(10.0, 20.0), (40.0, 20.0), (40.0, 50.0), (10.0, 50.0)]
    assert invert_polygon_affine(poly, None) == poly
    # Scale+translate forward; invert should restore
    forward = (2.0, 0.0, 5.0, 0.0, 2.0, 7.0)
    mapped = [(2 * x + 5, 2 * y + 7) for x, y in poly]
    restored = invert_polygon_affine(mapped, forward)
    for a, b in zip(poly, restored, strict=True):
        assert abs(a[0] - b[0]) < 1e-6
        assert abs(a[1] - b[1]) < 1e-6
