"""Word document validation for DOCX (untrusted ZIP) and legacy DOC (OLE).

DOCX packages are inspected in place: entries are never extracted to disk and
``extract``/``extractall`` are never called. Archive-safety limits guard against
zip bombs and path traversal, XML is parsed with ``defusedxml``, and macros are
rejected. Legacy DOC files are validated as OLE Word documents with macro
detection via ``oletools`` used as a library. Neither path extracts text.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from defusedxml.ElementTree import fromstring

from backend.app.contracts.errors import ErrorCode
from backend.app.settings.config import Settings
from backend.app.uploads.rejection import UploadRejected

_REQUIRED_ENTRIES = ("[Content_Types].xml", "word/document.xml")
_VBA_ENTRY = "word/vbaProject.bin"
_WORD_MAIN_CONTENT_TYPE = "wordprocessingml.document.main+xml"
_EXTERNAL_RELATIONSHIP_WARNING = "external_relationship"


def _is_unsafe_entry_name(name: str) -> bool:
    if "\x00" in name:
        return True
    if name.startswith("/") or name.startswith("\\"):
        return True
    if len(name) >= 2 and name[1] == ":":  # drive-qualified (e.g. C:\...)
        return True
    parts = name.replace("\\", "/").split("/")
    return ".." in parts


def _check_archive_safety(zf: zipfile.ZipFile, settings: Settings) -> None:
    infos = zf.infolist()
    if len(infos) > settings.max_docx_archive_entries:
        raise UploadRejected(ErrorCode.UPLOAD_ARCHIVE_TOO_LARGE, "Archive has too many entries.")
    total_uncompressed = 0
    for info in infos:
        if _is_unsafe_entry_name(info.filename):
            raise UploadRejected(
                ErrorCode.UPLOAD_ARCHIVE_UNSAFE, "Archive contains an unsafe entry path."
            )
        if info.flag_bits & 0x1:  # encrypted entry
            raise UploadRejected(
                ErrorCode.UPLOAD_ARCHIVE_UNSAFE, "Archive contains an encrypted entry."
            )
        if info.file_size > settings.max_docx_entry_bytes:
            raise UploadRejected(ErrorCode.UPLOAD_ARCHIVE_TOO_LARGE, "Archive entry is too large.")
        total_uncompressed += info.file_size
        if total_uncompressed > settings.max_docx_uncompressed_bytes:
            raise UploadRejected(
                ErrorCode.UPLOAD_ARCHIVE_TOO_LARGE, "Archive is too large uncompressed."
            )
        if info.compress_size > 0:
            ratio = info.file_size / info.compress_size
            if ratio > settings.max_docx_compression_ratio:
                raise UploadRejected(
                    ErrorCode.UPLOAD_ARCHIVE_TOO_LARGE, "Archive compression ratio is too high."
                )
        elif info.file_size > 0:
            # Non-empty entry with zero compressed size is malformed/suspicious.
            raise UploadRejected(ErrorCode.UPLOAD_ARCHIVE_UNSAFE, "Archive entry is malformed.")


def _validate_content_types(data: bytes) -> None:
    try:
        root = fromstring(data)
    except Exception:  # any XML error is a safe corruption signal
        raise UploadRejected(ErrorCode.UPLOAD_CORRUPT_FILE, "Invalid DOCX content types.") from None
    content_types = " ".join(element.get("ContentType", "") for element in root.iter())
    if "macroEnabled" in content_types:
        raise UploadRejected(
            ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED, "Macro-enabled documents are not supported."
        )
    if _WORD_MAIN_CONTENT_TYPE not in content_types:
        raise UploadRejected(
            ErrorCode.UPLOAD_CORRUPT_FILE, "File is not a WordprocessingML document."
        )


def _inspect_relationships(zf: zipfile.ZipFile, names: set[str]) -> list[str]:
    warnings: list[str] = []
    for name in names:
        if not name.endswith(".rels"):
            continue
        try:
            root = fromstring(zf.read(name))
        except Exception:  # ignore unreadable relationship parts
            continue
        for element in root.iter():
            if element.get("TargetMode") == "External":
                # Record only a safe marker; never the external URL.
                warnings.append(_EXTERNAL_RELATIONSHIP_WARNING)
                return warnings
    return warnings


def validate_docx(path: Path, settings: Settings) -> list[str]:
    """Validate a DOCX package and return safe warning markers."""

    try:
        with zipfile.ZipFile(path) as zf:
            _check_archive_safety(zf, settings)
            names = {info.filename for info in zf.infolist()}
            for required in _REQUIRED_ENTRIES:
                if required not in names:
                    raise UploadRejected(
                        ErrorCode.UPLOAD_CORRUPT_FILE, "DOCX is missing a required entry."
                    )
            if _VBA_ENTRY in names:
                raise UploadRejected(
                    ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED,
                    "Macro-enabled documents are not supported.",
                )
            _validate_content_types(zf.read("[Content_Types].xml"))
            return _inspect_relationships(zf, names)
    except UploadRejected:
        raise
    except zipfile.BadZipFile:
        raise UploadRejected(
            ErrorCode.UPLOAD_CORRUPT_FILE, "The DOCX archive is malformed."
        ) from None
    except OSError:
        raise UploadRejected(ErrorCode.UPLOAD_CORRUPT_FILE, "The DOCX could not be read.") from None


def validate_doc(path: Path) -> None:
    """Validate a legacy DOC as an OLE Word document without macros."""

    import olefile
    from oletools.olevba import VBA_Parser

    target = str(path)
    if not olefile.isOleFile(target):
        raise UploadRejected(
            ErrorCode.UPLOAD_SIGNATURE_MISMATCH, "File is not a valid legacy Word document."
        )

    ole = None
    try:
        ole = olefile.OleFileIO(target)
        streams = {"/".join(part.lower() for part in entry) for entry in ole.listdir()}
    except Exception:  # malformed OLE is a safe corruption signal
        raise UploadRejected(ErrorCode.UPLOAD_CORRUPT_FILE, "The DOC could not be read.") from None
    finally:
        if ole is not None:
            ole.close()

    if "worddocument" not in streams:
        raise UploadRejected(ErrorCode.UPLOAD_SIGNATURE_MISMATCH, "File is not a Word document.")

    parser = None
    try:
        parser = VBA_Parser(target)
        has_macros = parser.detect_vba_macros()
    except Exception:  # if macro safety cannot be established, reject
        raise UploadRejected(
            ErrorCode.UPLOAD_CORRUPT_FILE, "Could not scan the DOC for macros."
        ) from None
    finally:
        if parser is not None:
            parser.close()

    if has_macros:
        raise UploadRejected(
            ErrorCode.UPLOAD_MACROS_NOT_SUPPORTED, "Macro-enabled documents are not supported."
        )
