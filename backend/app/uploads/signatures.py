"""Magic-byte signature detection.

Client-supplied MIME and filename are never trusted. Every non-text format must
match an explicit byte signature; text is accepted only when it is not recognised
as any binary format and passes encoding validation elsewhere.
"""

from __future__ import annotations

from typing import Final

from backend.app.contracts.documents import DocumentFormat

_OLE_MAGIC: Final = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC: Final = b"\xff\xd8\xff"
_TIFF_LE: Final = b"II*\x00"
_TIFF_BE: Final = b"MM\x00*"
_BMP_MAGIC: Final = b"BM"
_ZIP_MAGICS: Final = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_PDF_MARKER: Final = b"%PDF-"
# Bounded window for the PDF marker (no unbounded search).
_PDF_MARKER_WINDOW: Final = 1024

# Extra binary signatures used to reject binaries masquerading as text.
_BINARY_PREFIXES: Final = (
    b"MZ",  # DOS/PE executable
    b"\x7fELF",  # ELF executable
    b"Rar!",  # RAR archive
    b"7z\xbc\xaf\x27\x1c",  # 7-Zip archive
    b"\x1f\x8b",  # gzip
    b"BZh",  # bzip2
)


def signature_matches(head: bytes, fmt: DocumentFormat) -> bool:
    """Return True when ``head`` matches the expected signature for ``fmt``."""

    match fmt:
        case DocumentFormat.PDF:
            return _PDF_MARKER in head[:_PDF_MARKER_WINDOW]
        case DocumentFormat.DOC:
            return head.startswith(_OLE_MAGIC)
        case DocumentFormat.DOCX:
            return head[:4] in _ZIP_MAGICS
        case DocumentFormat.JPEG:
            return head.startswith(_JPEG_MAGIC)
        case DocumentFormat.PNG:
            return head.startswith(_PNG_MAGIC)
        case DocumentFormat.TIFF:
            return head.startswith(_TIFF_LE) or head.startswith(_TIFF_BE)
        case DocumentFormat.BMP:
            return head.startswith(_BMP_MAGIC)
        case DocumentFormat.WEBP:
            return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
        case DocumentFormat.TXT:
            return True  # TXT has no binary signature; validated by encoding checks.


def detect(head: bytes) -> str | None:
    """Return a coarse, safe format label for diagnostics, or None."""

    if _PDF_MARKER in head[:_PDF_MARKER_WINDOW]:
        return "pdf"
    if head.startswith(_OLE_MAGIC):
        return "ole"
    if head[:4] in _ZIP_MAGICS:
        return "zip"
    if head.startswith(_JPEG_MAGIC):
        return "jpeg"
    if head.startswith(_PNG_MAGIC):
        return "png"
    if head.startswith(_TIFF_LE) or head.startswith(_TIFF_BE):
        return "tiff"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(_BMP_MAGIC):
        return "bmp"
    return None


def looks_binary(head: bytes) -> bool:
    """Return True when ``head`` looks like a known binary/archive/executable."""

    if detect(head) is not None:
        return True
    return any(head.startswith(prefix) for prefix in _BINARY_PREFIXES)
