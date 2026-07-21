"""Supported input formats, canonical media types and advisory client MIME sets.

Client-supplied MIME and filename are never trusted for acceptance; these tables
only decide the *allowlist* and the canonical media type recorded after signature
and structural validation prove the format.
"""

from __future__ import annotations

from typing import Final

from backend.app.contracts.documents import DocumentFormat

# Allowed extensions (with dot) surfaced to the UI, in a stable display order.
SUPPORTED_EXTENSIONS: Final = (
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
)

# Extension (without dot, lowercase) -> canonical internal format key.
EXTENSION_TO_FORMAT: Final[dict[str, DocumentFormat]] = {
    "pdf": DocumentFormat.PDF,
    "doc": DocumentFormat.DOC,
    "docx": DocumentFormat.DOCX,
    "txt": DocumentFormat.TXT,
    "jpg": DocumentFormat.JPEG,
    "jpeg": DocumentFormat.JPEG,
    "png": DocumentFormat.PNG,
    "tif": DocumentFormat.TIFF,
    "tiff": DocumentFormat.TIFF,
    "bmp": DocumentFormat.BMP,
    "webp": DocumentFormat.WEBP,
}

# Canonical, server-validated media type recorded on accepted documents.
FORMAT_MEDIA_TYPE: Final[dict[DocumentFormat, str]] = {
    DocumentFormat.PDF: "application/pdf",
    DocumentFormat.DOC: "application/msword",
    DocumentFormat.DOCX: (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    DocumentFormat.TXT: "text/plain",
    DocumentFormat.JPEG: "image/jpeg",
    DocumentFormat.PNG: "image/png",
    DocumentFormat.TIFF: "image/tiff",
    DocumentFormat.BMP: "image/bmp",
    DocumentFormat.WEBP: "image/webp",
}

_OCTET_STREAM: Final = "application/octet-stream"

# Advisory client MIME values accepted per format (a generic octet-stream is only
# accepted when signature + structural validation prove the format).
ALLOWED_CLIENT_MIME: Final[dict[DocumentFormat, frozenset[str]]] = {
    DocumentFormat.PDF: frozenset({"application/pdf", _OCTET_STREAM}),
    DocumentFormat.DOC: frozenset({"application/msword", _OCTET_STREAM}),
    DocumentFormat.DOCX: frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",
            _OCTET_STREAM,
        }
    ),
    DocumentFormat.TXT: frozenset({"text/plain", _OCTET_STREAM}),
    DocumentFormat.JPEG: frozenset({"image/jpeg", "image/pjpeg", _OCTET_STREAM}),
    DocumentFormat.PNG: frozenset({"image/png", _OCTET_STREAM}),
    DocumentFormat.TIFF: frozenset({"image/tiff", "image/x-tiff", _OCTET_STREAM}),
    DocumentFormat.BMP: frozenset({"image/bmp", "image/x-ms-bmp", _OCTET_STREAM}),
    DocumentFormat.WEBP: frozenset({"image/webp", _OCTET_STREAM}),
}


def is_supported_extension(extension: str) -> bool:
    """Return True when the dotless, lowercase extension is supported."""

    return extension in EXTENSION_TO_FORMAT
