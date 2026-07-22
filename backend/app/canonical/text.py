"""Deterministic TXT → PDF canonicalisation using ReportLab."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from backend.app.canonical.constants import (
    _FIXED_AUTHOR,
    _FIXED_CREATOR,
    _FIXED_PRODUCER,
    _FIXED_SUBJECT,
    _FIXED_TITLE,
)
from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.models import CanonicalisationResult
from backend.app.canonical.service import CanonicalisationService
from backend.app.contracts.canonical import CanonicalisationMethod, CanonicalPageSourceType
from backend.app.contracts.errors import ErrorCode
from backend.app.settings.config import Settings

_LETTER_WIDTH_POINTS = 612.0
_LETTER_HEIGHT_POINTS = 792.0


def detect_txt_encoding(head: bytes) -> str:
    """Detect UTF-8/UTF-16 encoding from an initial byte prefix."""

    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16"
    return "utf-8"


def canonicalise_text_pdf(
    *,
    settings: Settings,
    service: CanonicalisationService,
    session_id: str,
    document_id: str,
    job_id: str,
    original_path: Path,
    encoding: str | None = None,
    warnings: list[str] | None = None,
) -> tuple[CanonicalisationResult, str]:
    """Render a text file into a deterministic canonical PDF."""

    resolved_encoding = encoding or detect_txt_encoding(original_path.read_bytes()[:4])
    text = _read_normalised_text(original_path, resolved_encoding)
    staging_dir = service.staging_canonical_dir(session_id, job_id)
    staged_pdf = staging_dir / "text.pdf"
    _render_text_pdf(text, staged_pdf, settings)
    try:
        result = service.publish_atomic(
            session_id=session_id,
            document_id=document_id,
            staging_pdf=staged_pdf,
            method=CanonicalisationMethod.REPORTLAB_TEXT_PDF,
            source_type=CanonicalPageSourceType.TEXT,
            warnings=warnings,
        )
        return result, resolved_encoding
    finally:
        service.cleanup_staging(session_id, job_id)


def _read_normalised_text(path: Path, encoding: str) -> str:
    try:
        raw = path.read_bytes()
        decoded = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError) as exc:
        raise CanonicalisationError(
            ErrorCode.CANONICALISATION_FAILED,
            "Text encoding is not supported for canonicalisation.",
        ) from exc
    normalised = decoded.replace("\r\n", "\n").replace("\r", "\n")
    return normalised


def _render_text_pdf(text: str, destination: Path, settings: Settings) -> None:
    page_width, page_height = letter
    if page_width != _LETTER_WIDTH_POINTS or page_height != _LETTER_HEIGHT_POINTS:
        raise CanonicalisationError(
            ErrorCode.CONFIGURATION_ERROR,
            "TXT page size must be US Letter.",
        )

    margin = settings.txt_margin_points
    font_size = settings.txt_font_size_points
    leading = settings.txt_leading_points
    tab_size = settings.txt_tab_size
    content_width = page_width - (2 * margin)
    content_top = page_height - margin
    content_bottom = margin
    max_lines = max(1, int((content_top - content_bottom) // leading))

    buffer = BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=letter,
        bottomup=1,
        invariant=True,
        pageCompression=0,
    )
    pdf.setTitle(_FIXED_TITLE)
    pdf.setAuthor(_FIXED_AUTHOR)
    pdf.setCreator(_FIXED_CREATOR)
    pdf.setProducer(_FIXED_PRODUCER)
    pdf.setSubject(_FIXED_SUBJECT)
    pdf.setFont("Helvetica", font_size)

    lines_on_page = 0
    y = content_top - font_size

    def start_page() -> None:
        nonlocal lines_on_page, y
        if pdf.getPageNumber() > 1 or lines_on_page > 0:
            pdf.showPage()
            pdf.setFont("Helvetica", font_size)
        lines_on_page = 0
        y = content_top - font_size

    start_page()
    for paragraph in text.split("\f"):
        for raw_line in paragraph.split("\n"):
            wrapped = _wrap_line(raw_line, font_size, content_width, tab_size)
            if not wrapped:
                wrapped = [""]
            for line in wrapped:
                if lines_on_page >= max_lines:
                    start_page()
                _draw_line(pdf, line, margin, y, font_size, tab_size)
                y -= leading
                lines_on_page += 1
        if paragraph != text.split("\f")[-1]:
            start_page()

    pdf.save()
    destination.write_bytes(buffer.getvalue())


def _draw_line(
    pdf: canvas.Canvas,
    line: str,
    x: float,
    y: float,
    font_size: float,
    tab_size: int,
) -> None:
    cursor = x
    segments = line.split("\t")
    for index, segment in enumerate(segments):
        if segment:
            _assert_supported_glyphs(segment)
            pdf.drawString(cursor, y, segment)
            cursor += pdf.stringWidth(segment, "Helvetica", font_size)
        if index < len(segments) - 1:
            tab_width = pdf.stringWidth(" " * tab_size, "Helvetica", font_size)
            cursor = x + tab_width * max(1, int((cursor - x) // tab_width) + 1)


def _assert_supported_glyphs(text: str) -> None:
    for char in text:
        if char in ("\t", "\n", "\f"):
            continue
        try:
            char.encode("latin-1")
        except UnicodeEncodeError as exc:
            raise CanonicalisationError(
                ErrorCode.CANONICALISATION_UNSUPPORTED_TEXT_GLYPH,
                "Text contains characters that cannot be rendered deterministically.",
            ) from exc


def _wrap_line(line: str, font_size: float, max_width: float, tab_size: int) -> list[str]:
    if not line:
        return [""]
    expanded = line.expandtabs(tab_size)
    words = expanded.split(" ")
    wrapped: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        width = pdfmetrics.stringWidth(candidate, "Helvetica", font_size)
        if width <= max_width or not current:
            current = candidate
            continue
        wrapped.append(current)
        current = word
    if current or not wrapped:
        wrapped.append(current)
    return wrapped
