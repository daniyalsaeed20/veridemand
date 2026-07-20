"""Build classification features from document metadata and extraction artifacts."""

from __future__ import annotations

import re
from pathlib import Path

from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.enums import DocumentFileType, PageRoute
from app.models.source_span import SourceSpan
from app.services.classification.types import ClassificationFeatures

_NON_USABLE_FLAGS = frozenset(
    {
        "insufficient_coverage",
        "awaiting_ocr",
        "low_confidence",
        "broken_text_layer",
        "pathological_tokenization",
    }
)


def _tokenize_filename(name: str) -> tuple[str, ...]:
    stem = Path(name).stem.lower()
    parts = re.split(r"[^a-z0-9]+", stem)
    return tuple(p for p in parts if p)


def _page_usable(page: DocumentPage) -> bool:
    if page.ocr_status == "failed":
        return False
    if any(f in _NON_USABLE_FLAGS for f in page.quality_flags):
        return False
    if page.route == PageRoute.MANUAL_REVIEW and page.token_count in (0, None):
        return False
    return True


def _collect_early_text(
    pages: list[DocumentPage],
    spans_by_page: dict[int, list[SourceSpan]],
    *,
    max_pages: int = 3,
) -> tuple[str, tuple[str, ...], int, int]:
    texts: list[str] = []
    headings: list[str] = []
    usable = 0
    examined = 0
    for page in sorted(pages, key=lambda p: p.page_number)[:max_pages]:
        examined += 1
        if not _page_usable(page):
            continue
        usable += 1
        page_spans = spans_by_page.get(page.page_number, [])
        page_text = " ".join(s.text for s in page_spans if s.text.strip())
        if page_text:
            texts.append(page_text)
            first_line = page_text.split("\n", 1)[0].strip()
            if first_line and len(first_line) < 120:
                headings.append(first_line.lower())
    combined = " ".join(texts).lower()
    return combined, tuple(headings), usable, examined


def build_classification_features(
    document: Document,
    *,
    pages: list[DocumentPage] | None = None,
    spans_by_page: dict[int, list[SourceSpan]] | None = None,
) -> ClassificationFeatures:
    page_list = pages or []
    span_map = spans_by_page or {}
    early_text, headings, usable_count, examined = _collect_early_text(page_list, span_map)
    ext = Path(document.display_name).suffix.lstrip(".").lower() or document.file_type.value
    image_like = document.file_type in {
        DocumentFileType.JPG,
        DocumentFileType.PNG,
        DocumentFileType.TIFF,
    }
    return ClassificationFeatures(
        document_id=document.id,
        display_name=document.display_name,
        file_type=document.file_type,
        page_count=document.page_count or len(page_list) or 1,
        filename_tokens=_tokenize_filename(document.display_name),
        extension=ext,
        early_page_text=early_text,
        early_page_headings=headings,
        has_usable_text=bool(early_text.strip()),
        usable_page_count=usable_count,
        total_early_pages=examined,
        image_like=image_like,
    )
