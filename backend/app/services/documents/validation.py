"""Upload validation helpers: extension, MIME, signatures, DOCX ZIP limits."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from app.core.domain_errors import UploadFileError
from app.models.enums import DocumentFileType
from app.models.taxonomies import ErrorCode

# Decompression limits for DOCX (OOXML ZIP exception)
DOCX_MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024  # 200 MiB
DOCX_MAX_ENTRIES = 10_000
DOCX_MAX_COMPRESSION_RATIO = 100

ALLOWED_EXTENSIONS: dict[str, DocumentFileType] = {
    ".pdf": DocumentFileType.PDF,
    ".docx": DocumentFileType.DOCX,
    ".jpg": DocumentFileType.JPG,
    ".jpeg": DocumentFileType.JPG,
    ".png": DocumentFileType.PNG,
    ".tif": DocumentFileType.TIFF,
    ".tiff": DocumentFileType.TIFF,
}

ALLOWED_MIME: dict[DocumentFileType, frozenset[str]] = {
    DocumentFileType.PDF: frozenset({"application/pdf", "application/x-pdf"}),
    DocumentFileType.DOCX: frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/zip",  # some browsers
        }
    ),
    DocumentFileType.JPG: frozenset({"image/jpeg", "image/jpg"}),
    DocumentFileType.PNG: frozenset({"image/png"}),
    DocumentFileType.TIFF: frozenset({"image/tiff", "image/tif"}),
}

_MACRO_ENTRY_NAMES = frozenset(
    {
        "word/vbaproject.bin",
        "word/vbadata.xml",
    }
)

_MACRO_CONTENT_TYPE_MARKERS = (
    "vbaproject",
    "macroenabled",
    "vnd.ms-word.template.macroenabled",
    "vnd.ms-word.document.macroenabled",
)

_MACRO_RELATIONSHIP_MARKERS = (
    "vbaproject",
    "macrosheet",
)


def sanitize_display_name(filename: str | None) -> str:
    raw = (filename or "").strip() or "unnamed"
    # Drop any path components; reject traversal
    name = Path(raw.replace("\\", "/")).name
    if not name or name in {".", ".."} or ".." in name:
        raise UploadFileError(
            ErrorCode.UPLOAD_UNSUPPORTED_TYPE,
            display_name="invalid",
            message="Unsafe or empty filename.",
        )
    return name


def extension_for(filename: str) -> str:
    return Path(filename).suffix.lower()


def detect_signature(path: Path) -> DocumentFileType | None:
    with path.open("rb") as fh:
        header = fh.read(16)
    if header.startswith(b"%PDF"):
        return DocumentFileType.PDF
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return DocumentFileType.PNG
    if header.startswith(b"\xff\xd8\xff"):
        return DocumentFileType.JPG
    if header.startswith((b"II*\x00", b"MM\x00*")):
        return DocumentFileType.TIFF
    if header.startswith(b"PK\x03\x04") or header.startswith(b"PK\x05\x06"):
        # Likely ZIP / DOCX — confirmed by inspect_docx_zip
        return DocumentFileType.DOCX
    return None


def validate_extension_mime_signature(
    display_name: str,
    declared_mime: str | None,
    signature: DocumentFileType | None,
) -> DocumentFileType:
    ext = extension_for(display_name)
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadFileError(ErrorCode.UPLOAD_UNSUPPORTED_TYPE, display_name)
    expected = ALLOWED_EXTENSIONS[ext]
    mime = (declared_mime or "").split(";")[0].strip().lower()
    if mime and mime not in ALLOWED_MIME[expected] and mime != "application/octet-stream":
        raise UploadFileError(ErrorCode.UPLOAD_MIME_MISMATCH, display_name)
    if signature is None:
        raise UploadFileError(ErrorCode.UPLOAD_SIGNATURE_MISMATCH, display_name)
    if signature != expected:
        # JPEG extension vs PNG signature etc.
        if expected == DocumentFileType.DOCX and signature == DocumentFileType.DOCX:
            pass
        else:
            raise UploadFileError(ErrorCode.UPLOAD_SIGNATURE_MISMATCH, display_name)
    return expected


def hash_file_sha256(path: Path, chunk_size: int = 1_048_576) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def new_internal_filename(suffix: str) -> str:
    from app.services.session.workspace import new_opaque_id

    token = new_opaque_id("file").removeprefix("file_")
    safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    return f"{token}{safe_suffix}"


def assert_safe_zip_member_name(name: str) -> str:
    """Normalize and reject unsafe ZIP member names. Returns slash-normalized relative path."""
    if not name or "\x00" in name:
        raise UploadFileError(
            ErrorCode.UPLOAD_CORRUPT_FILE,
            "package",
            message="DOCX contains an invalid entry name.",
        )
    # Normalize backslashes before further checks
    normalized = name.replace("\\", "/")
    if normalized != name and ("\\" in name):
        # Already normalized; keep checking normalized form
        pass

    # Empty after strip
    if normalized == "" or name.strip() == "":
        raise UploadFileError(
            ErrorCode.UPLOAD_CORRUPT_FILE,
            "package",
            message="DOCX contains an invalid entry name.",
        )

    # Absolute POSIX
    if normalized.startswith("/"):
        raise UploadFileError(
            ErrorCode.UPLOAD_CORRUPT_FILE,
            "package",
            message="DOCX contains an unsafe entry path.",
        )

    # UNC //server/share or leading //
    if normalized.startswith("//"):
        raise UploadFileError(
            ErrorCode.UPLOAD_CORRUPT_FILE,
            "package",
            message="DOCX contains an unsafe entry path.",
        )

    # Drive-qualified: C:/..., C:..., etc.
    if re.match(r"^[A-Za-z]:", normalized):
        raise UploadFileError(
            ErrorCode.UPLOAD_CORRUPT_FILE,
            "package",
            message="DOCX contains an unsafe entry path.",
        )

    parts = normalized.split("/")
    for part in parts:
        if part == "..":
            raise UploadFileError(
                ErrorCode.UPLOAD_CORRUPT_FILE,
                "package",
                message="DOCX contains an unsafe entry path.",
            )

    return normalized


def _reject_macros(display: str = "package") -> None:
    raise UploadFileError(
        ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED,
        display,
        message="Macro-enabled Word documents are not supported.",
    )


def _xml_indicates_macros(payload: bytes) -> bool:
    text = payload.decode("utf-8", errors="ignore").lower()
    if any(marker in text for marker in _MACRO_CONTENT_TYPE_MARKERS):
        return True
    if any(marker in text for marker in _MACRO_RELATIONSHIP_MARKERS):
        return True
    # Also parse attributes when well-formed
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError:
        return any(
            marker in text
            for marker in (*_MACRO_CONTENT_TYPE_MARKERS, *_MACRO_RELATIONSHIP_MARKERS)
        )
    for elem in root.iter():
        for attr_val in elem.attrib.values():
            lower = attr_val.lower()
            if any(
                m in lower for m in (*_MACRO_CONTENT_TYPE_MARKERS, *_MACRO_RELATIONSHIP_MARKERS)
            ):
                return True
    return False


def inspect_docx_zip(
    path: Path,
    max_uncompressed_bytes: int = DOCX_MAX_UNCOMPRESSED_BYTES,
) -> None:
    """Validate OOXML ZIP structure with decompression bomb limits (no extract to disk)."""
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            if len(names) > DOCX_MAX_ENTRIES:
                raise UploadFileError(
                    ErrorCode.UPLOAD_CORRUPT_FILE,
                    path.name,
                    message="DOCX contains too many entries.",
                )
            total_uncompressed = 0
            has_content_types = False
            has_word = False
            for info in zf.infolist():
                name = assert_safe_zip_member_name(info.filename)
                if name.endswith(".zip"):
                    raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name)
                lower = name.lower()
                if lower in _MACRO_ENTRY_NAMES:
                    _reject_macros(path.name)
                if info.file_size > max_uncompressed_bytes:
                    raise UploadFileError(
                        ErrorCode.UPLOAD_CORRUPT_FILE,
                        path.name,
                        message="DOCX entry exceeds decompression limit.",
                    )
                if info.compress_size > 0:
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > DOCX_MAX_COMPRESSION_RATIO and info.file_size > 1_048_576:
                        raise UploadFileError(
                            ErrorCode.UPLOAD_CORRUPT_FILE,
                            path.name,
                            message="DOCX compression ratio exceeds limit.",
                        )
                total_uncompressed += info.file_size
                if total_uncompressed > max_uncompressed_bytes:
                    raise UploadFileError(
                        ErrorCode.UPLOAD_CORRUPT_FILE,
                        path.name,
                        message="DOCX uncompressed size exceeds limit.",
                    )
                if lower == "[content_types].xml":
                    has_content_types = True
                if lower.startswith("word/"):
                    has_word = True

            if not has_content_types or not has_word:
                raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name)

            # Macro markers in package XML (memory read only)
            for candidate in (
                "[Content_Types].xml",
                "_rels/.rels",
                "word/_rels/document.xml.rels",
            ):
                try:
                    payload = zf.read(candidate)
                except KeyError:
                    continue
                if _xml_indicates_macros(payload):
                    _reject_macros(path.name)
    except UploadFileError:
        raise
    except zipfile.BadZipFile as exc:
        raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name) from exc
    except OSError as exc:
        raise UploadFileError(ErrorCode.UPLOAD_CORRUPT_FILE, path.name) from exc
