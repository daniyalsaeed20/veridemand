"""Native extraction tests with synthetic text PDFs."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models.app_settings import AppSettings
from app.models.enums import PageRoute
from app.services.documents.image_pdf import write_blank_pdf, write_cropbox_pdf, write_rotated_pdf
from app.services.extraction.coordinates import screen_rect_from_normalized
from app.services.extraction.native import extract_native_page


def _write_text_pdf(path: Path, text: str = "CLAIMNUMBER") -> None:
    """Write a minimal PDF with a Helvetica Tj operator (pdfplumber-readable)."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 24 Tf 72 720 Td ({escaped}) Tj ET"
    length = len(stream.encode("latin-1"))
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        (
            b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
        ),
        (f"4 0 obj<< /Length {length} >>stream\n{stream}\nendstream\nendobj\n".encode("latin-1")),
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    trailer = f"trailer<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    out.extend(trailer.encode())
    path.write_bytes(bytes(out))


def test_native_word_and_char_coordinates(tmp_path: Path) -> None:
    pdf = tmp_path / "text.pdf"
    _write_text_pdf(pdf, "CLAIMNUMBER")
    settings = AppSettings(native_min_chars=5, native_min_text_coverage=0.0001)
    result = extract_native_page(
        pdf, document_id="doc_native0000000000000001", page_number=1, settings=settings
    )
    assert result.page.page_number == 1
    assert result.page.width > 0 and result.page.height > 0
    assert result.page.route.value == "native"
    assert len(result.tokens) >= 1
    assert any("CLAIM" in t.text for t in result.tokens)
    for token in result.tokens:
        for point in token.polygon:
            assert 0.0 <= point[0] <= 1.0
            assert 0.0 <= point[1] <= 1.0
        _, _, w1, _ = screen_rect_from_normalized(
            token.polygon, rendered_width=800, rendered_height=1000
        )
        _, _, w2, _ = screen_rect_from_normalized(
            token.polygon, rendered_width=1600, rendered_height=2000
        )
        assert w2 == pytest.approx(w1 * 2, rel=1e-6)


def test_empty_native_page_routes_without_ocr(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    write_blank_pdf(pdf)
    settings = AppSettings()
    result = extract_native_page(
        pdf, document_id="doc_blank00000000000000001", page_number=1, settings=settings
    )
    assert result.page.route in {PageRoute.MANUAL_REVIEW, PageRoute.OCR}
    assert result.page.ocr_status in {"pending", "not_needed"}
    assert result.tokens == []


def test_rotated_page_geometry(tmp_path: Path) -> None:
    pdf = tmp_path / "rot.pdf"
    write_rotated_pdf(pdf, rotation=90)
    settings = AppSettings()
    result = extract_native_page(
        pdf, document_id="doc_rot0000000000000000001", page_number=1, settings=settings
    )
    assert result.page.width > 0
    assert result.rotation in {0, 90, 180, 270}


def test_cropbox_page_opens(tmp_path: Path) -> None:
    pdf = tmp_path / "crop.pdf"
    write_cropbox_pdf(pdf)
    settings = AppSettings()
    result = extract_native_page(
        pdf, document_id="doc_crop000000000000000001", page_number=1, settings=settings
    )
    assert result.page.width > 0
    assert result.page.height > 0
