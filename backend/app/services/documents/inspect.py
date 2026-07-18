"""Document inspection: PDF encryption/corruption, image open, page counts."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.domain_errors import UploadFileError
from app.models.enums import DocumentFileType
from app.models.taxonomies import ErrorCode
from app.services.documents.validation import inspect_docx_zip


def inspect_and_count_pages(path: Path, file_type: DocumentFileType) -> int | None:
    """Validate file contents and return safe page count (None for DOCX in Phase 1)."""
    if file_type == DocumentFileType.PDF:
        return _inspect_pdf(path)
    if file_type == DocumentFileType.DOCX:
        inspect_docx_zip(path)
        return None
    if file_type in {DocumentFileType.JPG, DocumentFileType.PNG}:
        _inspect_image(path)
        return 1
    if file_type == DocumentFileType.TIFF:
        return _inspect_tiff(path)
    raise UploadFileError(ErrorCode.UPLOAD_UNSUPPORTED_TYPE, path.name)


def _inspect_pdf(path: Path) -> int:
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            # Try empty password; still treat as encrypted if locked
            try:
                unlocked: object = reader.decrypt("")
            except Exception:  # noqa: BLE001
                unlocked = 0
            if not unlocked:
                raise UploadFileError(ErrorCode.UPLOAD_ENCRYPTED_PDF, path.name)
        return len(reader.pages)
    except UploadFileError:
        raise
    except PdfReadError as exc:
        raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name) from exc
    except Exception as exc:  # noqa: BLE001
        raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name) from exc


def _inspect_image(path: Path) -> None:
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:  # noqa: BLE001
        raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name) from exc


def _inspect_tiff(path: Path) -> int:
    try:
        with Image.open(path) as img:
            count = 0
            while True:
                try:
                    img.seek(count)
                except EOFError:
                    break
                count += 1
            if count < 1:
                raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name)
            return count
    except UploadFileError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name) from exc
