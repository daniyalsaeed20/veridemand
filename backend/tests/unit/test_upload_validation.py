"""Unit tests for upload validation and inspection."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.domain_errors import UploadFileError
from app.models.enums import DocumentFileType
from app.models.taxonomies import ErrorCode
from app.services.documents.inspect import inspect_and_count_pages
from app.services.documents.validation import (
    DOCX_MAX_UNCOMPRESSED_BYTES,
    detect_signature,
    hash_file_sha256,
    inspect_docx_zip,
    sanitize_display_name,
    validate_extension_mime_signature,
)
from tests.fixtures.upload_builders import (
    write_corrupt_pdf,
    write_encrypted_pdf,
    write_exe_disguised_as_pdf,
    write_jpg,
    write_malformed_docx,
    write_minimal_docx,
    write_minimal_pdf,
    write_png,
    write_tiff,
    write_zip_bomb_docx,
)


def test_sanitize_rejects_traversal() -> None:
    assert sanitize_display_name("../../etc/passwd.pdf") == "passwd.pdf"
    with pytest.raises(UploadFileError):
        sanitize_display_name("..")


def test_signature_matrix(tmp_path: Path) -> None:
    pdf = write_minimal_pdf(tmp_path / "a.pdf")
    png = write_png(tmp_path / "a.png")
    jpg = write_jpg(tmp_path / "a.jpg")
    tiff = write_tiff(tmp_path / "a.tiff")
    docx = write_minimal_docx(tmp_path / "a.docx")
    assert detect_signature(pdf) == DocumentFileType.PDF
    assert detect_signature(png) == DocumentFileType.PNG
    assert detect_signature(jpg) == DocumentFileType.JPG
    assert detect_signature(tiff) == DocumentFileType.TIFF
    assert detect_signature(docx) == DocumentFileType.DOCX


def test_extension_mime_signature_mismatch(tmp_path: Path) -> None:
    png = write_png(tmp_path / "fake.pdf")
    sig = detect_signature(png)
    with pytest.raises(UploadFileError) as exc:
        validate_extension_mime_signature("fake.pdf", "application/pdf", sig)
    assert exc.value.error_code == ErrorCode.UPLOAD_SIGNATURE_MISMATCH


def test_unsupported_extension() -> None:
    with pytest.raises(UploadFileError) as exc:
        validate_extension_mime_signature("x.exe", "application/octet-stream", None)
    assert exc.value.error_code == ErrorCode.UPLOAD_UNSUPPORTED_TYPE


def test_pdf_encrypted_and_corrupt(tmp_path: Path) -> None:
    enc = write_encrypted_pdf(tmp_path / "enc.pdf")
    with pytest.raises(UploadFileError) as exc:
        inspect_and_count_pages(enc, DocumentFileType.PDF)
    assert exc.value.error_code == ErrorCode.UPLOAD_ENCRYPTED_PDF

    bad = write_corrupt_pdf(tmp_path / "bad.pdf")
    with pytest.raises(UploadFileError) as exc2:
        inspect_and_count_pages(bad, DocumentFileType.PDF)
    assert exc2.value.error_code == ErrorCode.UPLOAD_CORRUPT_FILE


def test_page_counts(tmp_path: Path) -> None:
    pdf = write_minimal_pdf(tmp_path / "p.pdf", pages=3)
    assert inspect_and_count_pages(pdf, DocumentFileType.PDF) == 3
    assert inspect_and_count_pages(write_png(tmp_path / "p.png"), DocumentFileType.PNG) == 1
    assert inspect_and_count_pages(write_jpg(tmp_path / "p.jpg"), DocumentFileType.JPG) == 1
    tiff_pages = inspect_and_count_pages(
        write_tiff(tmp_path / "p.tiff", frames=3), DocumentFileType.TIFF
    )
    assert tiff_pages == 3
    docx = write_minimal_docx(tmp_path / "p.docx")
    assert inspect_and_count_pages(docx, DocumentFileType.DOCX) is None


def test_docx_malformed_and_bomb(tmp_path: Path) -> None:
    bad = write_malformed_docx(tmp_path / "bad.docx")
    with pytest.raises(UploadFileError):
        inspect_docx_zip(bad)

    bomb = write_zip_bomb_docx(tmp_path / "bomb.docx")
    with pytest.raises(UploadFileError):
        inspect_docx_zip(bomb, max_uncompressed_bytes=5 * 1024 * 1024)


def test_exe_as_pdf_signature(tmp_path: Path) -> None:
    path = write_exe_disguised_as_pdf(tmp_path / "x.pdf")
    assert detect_signature(path) is None


def test_sha256_deterministic(tmp_path: Path) -> None:
    path = write_minimal_pdf(tmp_path / "h.pdf")
    assert hash_file_sha256(path) == hash_file_sha256(path)


def test_docx_limit_constant() -> None:
    assert DOCX_MAX_UNCOMPRESSED_BYTES >= 1_000_000
