"""Helpers to build synthetic upload fixtures for tests."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image
from pypdf import PdfWriter


def write_minimal_pdf(path: Path, *, pages: int = 1) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def write_ocr_routed_pdf(path: Path) -> Path:
    """Synthetic PDF whose native text fails usability and routes to OCR (no PII)."""
    # Long glued token triggers pathological_tokenization → PageRoute.ocr.
    # noqa: E501 — PDF object dictionary lines are intentionally single-line.
    path.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n"
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n"
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
        b"4 0 obj<< /Length 68 >>stream\n"
        b"BT /F1 12 Tf 10 100 Td (HelloWorldBrokenTextLayerXXXX) Tj ET\n"
        b"endstream\n"
        b"endobj\n"
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000385 00000 n \n"
        b"trailer<< /Size 6 /Root 1 0 R >>\n"
        b"startxref\n"
        b"462\n"
        b"%%EOF\n"
    )
    return path


def write_encrypted_pdf(path: Path) -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret-password")
    with path.open("wb") as fh:
        writer.write(fh)
    return path


def write_corrupt_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\nnot a real pdf body\n%%EOF\n")
    return path


def write_png(path: Path, size: tuple[int, int] = (8, 8)) -> Path:
    img = Image.new("RGB", size, color=(20, 40, 60))
    img.save(path, format="PNG")
    return path


def write_jpg(path: Path, size: tuple[int, int] = (8, 8)) -> Path:
    img = Image.new("RGB", size, color=(200, 100, 50))
    img.save(path, format="JPEG", quality=90)
    return path


def write_tiff(path: Path, frames: int = 2) -> Path:
    frames_imgs = [Image.new("RGB", (8, 8), color=(i * 40, 10, 10)) for i in range(frames)]
    frames_imgs[0].save(
        path,
        format="TIFF",
        save_all=True,
        append_images=frames_imgs[1:],
    )
    return path


def write_exe_disguised_as_pdf(path: Path) -> Path:
    path.write_bytes(b"MZ\x90\x00fake-exe-content")
    return path


def _docx_skeleton(
    *,
    extra_entries: dict[str, bytes] | None = None,
    content_types: str | None = None,
    package_rels: str | None = None,
    document_rels: str | None = None,
) -> bytes:
    default_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>hello</w:t></w:r></w:p></w:body></w:document>"
    )
    default_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types or default_types)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("_rels/.rels", package_rels or default_rels)
        if document_rels is not None:
            zf.writestr("word/_rels/document.xml.rels", document_rels)
        if extra_entries:
            for name, payload in extra_entries.items():
                zf.writestr(name, payload)
    return buf.getvalue()


def write_minimal_docx(path: Path) -> Path:
    path.write_bytes(_docx_skeleton())
    return path


def write_docx_with_entry(path: Path, entry_name: str, payload: bytes = b"x") -> Path:
    """Build a DOCX-like ZIP that includes an extra (possibly unsafe) member name."""
    # Use ZipInfo to preserve unusual names ZipFile might otherwise alter
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", "<w:document/>")
        info = zipfile.ZipInfo(entry_name)
        zf.writestr(info, payload)
    return path


def write_docx_with_vbaproject(path: Path) -> Path:
    path.write_bytes(_docx_skeleton(extra_entries={"word/vbaProject.bin": b"\x00" * 64}))
    return path


def write_docx_with_vba_content_type(path: Path) -> Path:
    types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/hiddenVba.bin" '
        'ContentType="application/vnd.ms-office.vbaProject"/>'
        "</Types>"
    )
    path.write_bytes(
        _docx_skeleton(content_types=types, extra_entries={"word/hiddenVba.bin": b"\x00"})
    )
    return path


def write_docx_with_vba_relationship(path: Path) -> Path:
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdVba" '
        'Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" '
        'Target="hidden.bin"/>'
        "</Relationships>"
    )
    path.write_bytes(
        _docx_skeleton(
            document_rels=doc_rels,
            extra_entries={"word/hidden.bin": b"\x00"},
        )
    )
    return path


def write_macro_enabled_as_docx(path: Path) -> Path:
    """Simulate a .docm package renamed to .docx (macro content types)."""
    types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.ms-word.document.macroEnabled.main+xml"/>'
        "</Types>"
    )
    path.write_bytes(
        _docx_skeleton(
            content_types=types,
            extra_entries={"word/vbaProject.bin": b"\x00" * 32},
        )
    )
    return path


def write_malformed_docx(path: Path) -> Path:
    # ZIP without required OOXML parts
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "not a docx")
    return path


def write_zip_bomb_docx(path: Path) -> Path:
    """Highly compressible payload that exceeds decompression limits when inspected."""
    payload = b"0" * (2 * 1024 * 1024)  # 2 MiB zeros compresses tiny
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        for i in range(120):
            zf.writestr(f"word/pad_{i}.bin", payload)
    return path
