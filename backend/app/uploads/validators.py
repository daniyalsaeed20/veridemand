"""Format-specific structural validation.

Uses ``pypdf`` and ``Pillow`` strictly for validation: opening, encryption and
page-count checks for PDFs; format, integrity, dimension, pixel and frame checks
for images. Neither library extracts text, renders pages, or processes content.
"""

from __future__ import annotations

import codecs
import unicodedata
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from PIL import Image, UnidentifiedImageError

from backend.app.contracts.documents import DocumentFormat, PageCountStatus
from backend.app.contracts.errors import ErrorCode
from backend.app.settings.config import Settings
from backend.app.uploads import signatures, word_validation
from backend.app.uploads.rejection import UploadRejected

# Fraction of non-whitespace control characters above which text is rejected.
_MAX_TXT_CONTROL_RATIO: Final = 0.30
_TXT_CHUNK_BYTES: Final = 65_536
_ALLOWED_TXT_CONTROL: Final = frozenset({"\t", "\n", "\r", "\f", "\v"})

_IMAGE_FORMATS: Final = frozenset(
    {
        DocumentFormat.JPEG,
        DocumentFormat.PNG,
        DocumentFormat.TIFF,
        DocumentFormat.BMP,
        DocumentFormat.WEBP,
    }
)

_PIL_FORMAT_NAMES: Final[dict[DocumentFormat, frozenset[str]]] = {
    DocumentFormat.JPEG: frozenset({"JPEG"}),
    DocumentFormat.PNG: frozenset({"PNG"}),
    DocumentFormat.TIFF: frozenset({"TIFF"}),
    DocumentFormat.BMP: frozenset({"BMP", "DIB"}),
    DocumentFormat.WEBP: frozenset({"WEBP"}),
}


@dataclass
class StructureResult:
    """Outcome of structural validation."""

    page_count: int | None
    page_count_status: PageCountStatus
    warnings: list[str] = field(default_factory=list)


def validate_pdf(path: Path) -> int:
    """Validate a PDF and return its page count. Never extracts text/renders."""

    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            raise UploadRejected(
                ErrorCode.UPLOAD_ENCRYPTED_PDF, "Encrypted PDFs are not supported."
            )
        page_count = len(reader.pages)
    except UploadRejected:
        raise
    except (PdfReadError, ValueError, OSError, EOFError):
        raise UploadRejected(ErrorCode.UPLOAD_CORRUPT_FILE, "The PDF could not be read.") from None
    except Exception:  # translate any parser error into a safe code
        raise UploadRejected(ErrorCode.UPLOAD_CORRUPT_FILE, "The PDF could not be read.") from None

    if page_count < 1:
        raise UploadRejected(ErrorCode.UPLOAD_CORRUPT_FILE, "The PDF has no readable pages.")
    return page_count


def validate_image(path: Path, fmt: DocumentFormat, *, max_pixels: int) -> int:
    """Validate an image and return its frame (page) count."""

    expected = _PIL_FORMAT_NAMES[fmt]
    # Align Pillow's decompression-bomb threshold with our configured limit.
    Image.MAX_IMAGE_PIXELS = max_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in expected:
                    raise UploadRejected(
                        ErrorCode.UPLOAD_SIGNATURE_MISMATCH,
                        "Image contents do not match the file extension.",
                        detected_format=(image.format or "").lower() or None,
                    )
                width, height = image.size
                if width < 1 or height < 1 or width * height > max_pixels:
                    raise UploadRejected(
                        ErrorCode.UPLOAD_IMAGE_TOO_LARGE,
                        "Image exceeds the maximum allowed pixel count.",
                    )
                frames = int(getattr(image, "n_frames", 1))
                if frames < 1:
                    raise UploadRejected(
                        ErrorCode.UPLOAD_CORRUPT_FILE, "Image has no readable frames."
                    )
            # Re-open on a fresh handle to verify structural integrity.
            with Image.open(path) as verifier:
                verifier.verify()
    except UploadRejected:
        raise
    except Image.DecompressionBombError:
        raise UploadRejected(
            ErrorCode.UPLOAD_IMAGE_TOO_LARGE, "Image exceeds the maximum allowed pixel count."
        ) from None
    except Image.DecompressionBombWarning:
        raise UploadRejected(
            ErrorCode.UPLOAD_IMAGE_TOO_LARGE, "Image exceeds the maximum allowed pixel count."
        ) from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise UploadRejected(
            ErrorCode.UPLOAD_CORRUPT_FILE, "The image could not be read."
        ) from None
    return frames


def _detect_txt_encoding(head: bytes) -> str:
    if head.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff"):
        return "utf-16"
    return "utf-8"


def validate_txt(path: Path) -> None:
    """Validate that a file is safe, decodable text (never extracts content)."""

    with path.open("rb") as handle:
        head = handle.read(4)

    if signatures.looks_binary(head):
        raise UploadRejected(
            ErrorCode.UPLOAD_SIGNATURE_MISMATCH, "File is a binary format, not text."
        )

    encoding = _detect_txt_encoding(head)
    decoder = codecs.getincrementaldecoder(encoding)()
    total = 0
    control = 0
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(_TXT_CHUNK_BYTES)
                final = not chunk
                text = decoder.decode(chunk, final)
                for char in text:
                    total += 1
                    if char == "\x00":
                        raise UploadRejected(
                            ErrorCode.UPLOAD_CORRUPT_FILE, "Text contains NUL bytes."
                        )
                    if char not in _ALLOWED_TXT_CONTROL and unicodedata.category(char) == "Cc":
                        control += 1
                if final:
                    break
    except UploadRejected:
        raise
    except (UnicodeDecodeError, LookupError):
        raise UploadRejected(
            ErrorCode.UPLOAD_CORRUPT_FILE, "Text is not valid UTF-8/UTF-16."
        ) from None

    if total == 0:
        raise UploadRejected(ErrorCode.UPLOAD_CORRUPT_FILE, "Text file is empty.")
    if control / total > _MAX_TXT_CONTROL_RATIO:
        raise UploadRejected(
            ErrorCode.UPLOAD_CORRUPT_FILE, "Text contains too many control characters."
        )


def validate_structure(path: Path, fmt: DocumentFormat, settings: Settings) -> StructureResult:
    """Dispatch structural validation and return page-count metadata."""

    if fmt is DocumentFormat.PDF:
        return StructureResult(validate_pdf(path), PageCountStatus.KNOWN)
    if fmt in _IMAGE_FORMATS:
        frames = validate_image(path, fmt, max_pixels=settings.max_image_pixels)
        return StructureResult(frames, PageCountStatus.KNOWN)
    if fmt is DocumentFormat.TXT:
        validate_txt(path)
        return StructureResult(None, PageCountStatus.PENDING_CANONICALISATION)
    if fmt is DocumentFormat.DOCX:
        found = word_validation.validate_docx(path, settings)
        return StructureResult(None, PageCountStatus.PENDING_CANONICALISATION, found)
    if fmt is DocumentFormat.DOC:
        word_validation.validate_doc(path)
        return StructureResult(None, PageCountStatus.PENDING_CANONICALISATION)
    raise UploadRejected(ErrorCode.UPLOAD_UNSUPPORTED_TYPE, "Unsupported document type.")
