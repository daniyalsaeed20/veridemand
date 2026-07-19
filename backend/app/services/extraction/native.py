"""Native PDF text extraction via pdfplumber (FR-EXT-01)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from app.models.app_settings import AppSettings
from app.models.document_page import DocumentPage
from app.models.enums import ExtractionMethod, PageRoute
from app.models.source_span import SourceSpan
from app.models.source_token import SourceToken
from app.services.extraction.coordinates import (
    PageGeometry,
    pdfplumber_bbox_to_normalized_quad,
)
from app.services.extraction.routing import (
    NativeWord,
    PageDiagnostics,
    score_native_text_usability,
    select_page_route,
)
from app.services.extraction.spans import group_tokens_into_spans
from app.services.session.workspace import new_opaque_id


@dataclass
class NativePageResult:
    page: DocumentPage
    tokens: list[SourceToken]
    spans: list[SourceSpan]
    diagnostics: PageDiagnostics
    rotation: int = 0
    geometry_warnings: list[str] = field(default_factory=list)


def extract_native_page(
    canonical_pdf: Path,
    *,
    document_id: str,
    page_number: int,
    settings: AppSettings,
) -> NativePageResult:
    """Extract one 1-based page: tokens, spans, routing (no OCR)."""
    with pdfplumber.open(canonical_pdf) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise IndexError(f"page_number out of range: {page_number}")
        plumber_page = pdf.pages[page_number - 1]
        geom = _page_geometry(plumber_page)
        words_raw = (
            plumber_page.extract_words(
                use_text_flow=True,
                keep_blank_chars=False,
                extra_attrs=["size"],
            )
            or []
        )

        native_words: list[NativeWord] = []
        for w in words_raw:
            native_words.append(
                NativeWord(
                    text=str(w.get("text") or ""),
                    x0=float(w["x0"]),
                    top=float(w["top"]),
                    x1=float(w["x1"]),
                    bottom=float(w["bottom"]),
                    width=max(0.0, float(w["x1"]) - float(w["x0"])),
                    height=max(0.0, float(w["bottom"]) - float(w["top"])),
                )
            )

        image_coverage = _estimate_image_coverage(plumber_page, geom)
        diagnostics = score_native_text_usability(
            native_words,
            page_width=geom.width,
            page_height=geom.height,
            image_coverage=image_coverage,
            settings=settings,
        )
        route = select_page_route(diagnostics, settings)

        tokens: list[SourceToken] = []
        geometry_warnings: list[str] = []
        if route == PageRoute.NATIVE:
            for word in native_words:
                quad = pdfplumber_bbox_to_normalized_quad(
                    word.x0, word.top, word.x1, word.bottom, geom
                )
                if quad is None:
                    geometry_warnings.append("token_geometry_rejected")
                    continue
                tokens.append(
                    SourceToken(
                        id=new_opaque_id("tok"),
                        document_id=document_id,
                        page_number=page_number,
                        text=word.text,
                        confidence=1.0,
                        polygon=quad,
                        method=ExtractionMethod.NATIVE,
                    )
                )
            spans = group_tokens_into_spans(tokens)
            method: ExtractionMethod | None = ExtractionMethod.NATIVE
            ocr_status = "not_needed"
        else:
            spans = []
            method = None
            ocr_status = "pending" if route == PageRoute.OCR else "not_needed"
            if route == PageRoute.OCR:
                diagnostics.quality_flags = list(
                    dict.fromkeys([*diagnostics.quality_flags, "awaiting_ocr"])
                )

        if geometry_warnings:
            diagnostics.warnings.extend(geometry_warnings)
            if "broken_text_layer" not in diagnostics.quality_flags and len(
                geometry_warnings
            ) > max(1, len(native_words) // 2):
                diagnostics.quality_flags.append("broken_text_layer")

        page = DocumentPage(
            id=f"page_{document_id}_{page_number}",
            document_id=document_id,
            page_number=page_number,
            width=geom.width,
            height=geom.height,
            text_coverage=diagnostics.text_coverage,
            route=route,
            ocr_status=ocr_status,
            extraction_method=method,
            quality_flags=list(dict.fromkeys(diagnostics.quality_flags)),
            token_count=len(tokens),
            span_count=len(spans),
        )
        return NativePageResult(
            page=page,
            tokens=tokens,
            spans=spans,
            diagnostics=diagnostics,
            rotation=geom.rotation,
            geometry_warnings=geometry_warnings,
        )


def extract_document_native(
    canonical_pdf: Path,
    *,
    document_id: str,
    settings: AppSettings,
) -> list[NativePageResult]:
    with pdfplumber.open(canonical_pdf) as pdf:
        count = len(pdf.pages)
    return [
        extract_native_page(
            canonical_pdf,
            document_id=document_id,
            page_number=n,
            settings=settings,
        )
        for n in range(1, count + 1)
    ]


def _page_geometry(page: object) -> PageGeometry:
    """Prefer CropBox dimensions when available; capture /Rotate."""
    width = float(getattr(page, "width", 0) or 0)
    height = float(getattr(page, "height", 0) or 0)
    rotation = int(getattr(page, "rotation", 0) or 0) % 360
    crop_x0 = 0.0
    crop_y0 = 0.0

    # pdfplumber page.width/height already reflect the visible box in most cases.
    # When CropBox differs, mediabox/cropbox attrs may be present.
    crop = getattr(page, "cropbox", None) or getattr(page, "crop_box", None)
    media = getattr(page, "mediabox", None) or getattr(page, "media_box", None)
    if crop is not None and media is not None:
        try:
            # Objects may be lists [x0,y0,x1,y1] or have attributes
            if hasattr(crop, "x0"):
                cx0, cy0, cx1, cy1 = (
                    float(crop.x0),
                    float(crop.y0),
                    float(crop.x1),
                    float(crop.y1),
                )
            else:
                cx0, cy0, cx1, cy1 = (float(v) for v in crop)
            width = max(cx1 - cx0, 1.0)
            height = max(cy1 - cy0, 1.0)
            crop_x0 = cx0
            crop_y0 = cy0
        except (TypeError, ValueError, AttributeError):
            pass

    if width <= 0 or height <= 0:
        width = max(width, 1.0)
        height = max(height, 1.0)

    # pdfplumber presents a rotated visual page; keep rotation for overlay tests
    return PageGeometry(
        width=width,
        height=height,
        crop_x0=crop_x0,
        crop_y0=crop_y0,
        rotation=rotation,
    )


def _estimate_image_coverage(page: object, geom: PageGeometry) -> float:
    page_area = max(geom.width * geom.height, 1.0)
    images = getattr(page, "images", None) or []
    area = 0.0
    for img in images:
        try:
            w = abs(float(img.get("x1", 0)) - float(img.get("x0", 0)))
            h = abs(
                float(img.get("bottom", img.get("y1", 0))) - float(img.get("top", img.get("y0", 0)))
            )
            area += w * h
        except (TypeError, ValueError, AttributeError):
            continue
    return min(1.0, area / page_area)
