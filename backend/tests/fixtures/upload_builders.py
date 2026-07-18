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


def write_minimal_docx(path: Path) -> Path:
    content_types = (
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
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("_rels/.rels", rels)
    path.write_bytes(buf.getvalue())
    return path


def write_malformed_docx(path: Path) -> Path:
    # ZIP without required OOXML parts
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("readme.txt", "not a docx")
    return path


def write_zip_bomb_docx(path: Path) -> Path:
    """Highly compressible payload that exceeds decompression limits when inspected."""
    # Create a zip with one huge sparse-looking repeated entry
    payload = b"0" * (2 * 1024 * 1024)  # 2 MiB zeros compresses tiny
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        # Write many copies to blow uncompressed total past limit when using low max
        for i in range(120):
            zf.writestr(f"word/pad_{i}.bin", payload)
    return path


def write_exe_disguised_as_pdf(path: Path) -> Path:
    path.write_bytes(b"MZ\x90\x00fake-exe-content")
    return path
