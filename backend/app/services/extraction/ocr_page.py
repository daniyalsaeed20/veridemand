"""OCR page orchestration: render → preprocess → OCR → tokens/spans → quality.

Does not import PaddleOCR directly; uses the approved OCR adapter.
Does not hold SessionService or PDFium locks across OCR inference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from app.models.app_settings import AppSettings
from app.models.document_page import DocumentPage
from app.models.enums import ExtractionMethod, PageRoute
from app.models.source_span import SourceSpan
from app.models.source_token import SourceToken
from app.services.documents.pdfium_runtime import PdfiumRuntimeError, render_page
from app.services.extraction.coordinates import image_polygon_to_normalized
from app.services.extraction.ocr_quality import (
    OcrPageOutcome,
    OcrQualityAssessment,
    assess_ocr_tokens,
    score_pass_for_retry_choice,
)
from app.services.extraction.preprocess import maybe_preprocess
from app.services.extraction.spans import group_tokens_into_spans
from app.services.ocr import (
    OcrCancelledError,
    OcrRawResult,
    OcrUnavailableError,
    recognize_image,
)
from app.services.session.workspace import new_opaque_id

# Prototype bound on rendered pixels (width*height) to limit memory.
_MAX_RENDER_PIXELS = 8_000_000
_MAX_EDGE = 4500


@dataclass
class OcrRenderMeta:
    dpi: int
    width: int
    height: int
    rotation: int
    preprocess_path: str
    elapsed_render_ms: float = 0.0
    elapsed_ocr_ms: float = 0.0


@dataclass
class OcrPageResult:
    page: DocumentPage
    tokens: list[SourceToken]
    spans: list[SourceSpan]
    assessment: OcrQualityAssessment
    render_meta: OcrRenderMeta
    retried: bool = False
    error_code: str | None = None
    warnings: list[str] = field(default_factory=list)


def extract_ocr_page(
    canonical_pdf: Path,
    *,
    document_id: str,
    page: DocumentPage,
    settings: AppSettings,
    page_rotation: int = 0,
    force_ocr: bool = False,
) -> OcrPageResult:
    """Run OCR for one routed page. Caller must not hold session/PDFium locks."""
    if page.route != PageRoute.OCR and not force_ocr:
        raise ValueError("extract_ocr_page requires PageRoute.ocr unless force_ocr")

    first = _run_pass(
        canonical_pdf,
        document_id=document_id,
        page=page,
        settings=settings,
        page_rotation=page_rotation,
        dpi=settings.ocr_render_dpi,
        preprocess_force=False,
    )
    assessment = assess_ocr_tokens(
        first.tokens,
        settings=settings,
        engine_warnings=first.warnings,
    )

    need_retry = (
        assessment.mean_confidence is not None
        and assessment.mean_confidence < settings.ocr_page_mean_conf_retry_trigger
    ) or assessment.outcome in {OcrPageOutcome.BLANK, OcrPageOutcome.LOW_CONFIDENCE}

    if not need_retry:
        return _finalize(page, first, assessment, retried=False)

    second = _run_pass(
        canonical_pdf,
        document_id=document_id,
        page=page,
        settings=settings,
        page_rotation=page_rotation,
        dpi=settings.ocr_retry_dpi,
        preprocess_force=True,
    )
    score_first = score_pass_for_retry_choice(first.tokens, settings=settings)
    score_second = score_pass_for_retry_choice(second.tokens, settings=settings)
    chosen = second if score_second >= score_first else first
    chosen_assessment = assess_ocr_tokens(
        chosen.tokens,
        settings=settings,
        engine_warnings=chosen.warnings,
    )
    return _finalize(page, chosen, chosen_assessment, retried=True)


def _finalize(
    page: DocumentPage,
    pass_result: _PassBundle,
    assessment: OcrQualityAssessment,
    *,
    retried: bool,
) -> OcrPageResult:
    flags = [f for f in page.quality_flags if f not in {"awaiting_ocr"}]
    flags.extend(assessment.quality_flags)
    flags = list(dict.fromkeys(flags))

    if assessment.outcome in {OcrPageOutcome.BLANK, OcrPageOutcome.FAILED}:
        ocr_status = "failed" if assessment.outcome == OcrPageOutcome.FAILED else "done"
        tokens: list[SourceToken] = []
        spans: list[SourceSpan] = []
    else:
        ocr_status = "done"
        tokens = pass_result.tokens
        spans = pass_result.spans

    updated = page.model_copy(
        deep=True,
        update={
            "ocr_status": ocr_status,
            "extraction_method": ExtractionMethod.OCR if tokens else page.extraction_method,
            "quality_flags": flags,
            "token_count": len(tokens),
            "span_count": len(spans),
            "text_coverage": assessment.coverage if tokens else page.text_coverage,
            "route": PageRoute.OCR,
        },
    )
    return OcrPageResult(
        page=updated,
        tokens=tokens,
        spans=spans,
        assessment=assessment,
        render_meta=pass_result.meta,
        retried=retried,
        warnings=list(dict.fromkeys([*pass_result.warnings, *assessment.warnings])),
    )


@dataclass
class _PassBundle:
    tokens: list[SourceToken]
    spans: list[SourceSpan]
    meta: OcrRenderMeta
    warnings: list[str]
    raw: OcrRawResult | None = None


def _run_pass(
    canonical_pdf: Path,
    *,
    document_id: str,
    page: DocumentPage,
    settings: AppSettings,
    page_rotation: int,
    dpi: int,
    preprocess_force: bool,
) -> _PassBundle:
    import time

    t0 = time.perf_counter()
    image = _render_bounded(canonical_pdf, page_number=page.page_number, dpi=dpi)
    render_ms = (time.perf_counter() - t0) * 1000.0

    prepared = maybe_preprocess(image, force=preprocess_force, low_contrast=preprocess_force)
    image.close()

    try:
        raw = recognize_image(prepared.image)
    except OcrCancelledError:
        prepared.image.close()
        raise
    except OcrUnavailableError as exc:
        prepared.image.close()
        meta = OcrRenderMeta(
            dpi=dpi,
            width=0,
            height=0,
            rotation=page_rotation,
            preprocess_path=prepared.path_name,
            elapsed_render_ms=render_ms,
        )
        return _PassBundle(tokens=[], spans=[], meta=meta, warnings=[str(exc)])

    width, height = prepared.image.size
    tokens = detections_to_tokens(
        raw,
        document_id=document_id,
        page_number=page.page_number,
        image_width=width,
        image_height=height,
        page_rotation=0,  # bitmap already matches viewer orientation
    )
    spans = group_tokens_into_spans(tokens)
    prepared.image.close()

    meta = OcrRenderMeta(
        dpi=dpi,
        width=width,
        height=height,
        rotation=page_rotation,
        preprocess_path=prepared.path_name,
        elapsed_render_ms=render_ms,
        elapsed_ocr_ms=raw.elapsed_ms,
    )
    return _PassBundle(
        tokens=tokens,
        spans=spans,
        meta=meta,
        warnings=list(raw.warnings),
        raw=raw,
    )


def detections_to_tokens(
    raw: OcrRawResult,
    *,
    document_id: str,
    page_number: int,
    image_width: int,
    image_height: int,
    page_rotation: int = 0,
) -> list[SourceToken]:
    tokens: list[SourceToken] = []
    for det in raw.detections:
        if not det.text or not det.text.strip():
            continue
        polygon = image_polygon_to_normalized(
            det.polygon_px,
            image_width=image_width,
            image_height=image_height,
            page_rotation=page_rotation,
            clamp=True,
        )
        if polygon is None:
            continue
        tokens.append(
            SourceToken(
                id=new_opaque_id("tok"),
                document_id=document_id,
                page_number=page_number,
                text=det.text.strip(),
                confidence=det.confidence,
                polygon=polygon,
                method=ExtractionMethod.OCR,
            )
        )
    return tokens


def _render_bounded(canonical_pdf: Path, *, page_number: int, dpi: int) -> Image.Image:
    scale = dpi / 72.0
    try:
        image = render_page(canonical_pdf, page_index=page_number - 1, scale=scale)
    except PdfiumRuntimeError as exc:
        raise OcrUnavailableError("Page render for OCR failed.") from exc

    w, h = image.size
    pixels = w * h
    if pixels > _MAX_RENDER_PIXELS or w > _MAX_EDGE or h > _MAX_EDGE:
        factor = min(
            (_MAX_RENDER_PIXELS / max(pixels, 1)) ** 0.5,
            _MAX_EDGE / max(w, 1),
            _MAX_EDGE / max(h, 1),
        )
        if factor < 1.0:
            nw = max(1, int(w * factor))
            nh = max(1, int(h * factor))
            resized = image.resize((nw, nh), Image.Resampling.BILINEAR)
            image.close()
            return resized
    return image
