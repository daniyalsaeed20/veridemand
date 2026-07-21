"""Filename normalisation.

The normalised *display* filename is metadata only and is never used as a
filesystem path. Only the final basename is considered; path components, NUL
bytes and control characters are removed; Unicode is normalised to NFC; and the
extension is lowercased for validation. Double extensions are not trusted: only
the final extension is used.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from backend.app.contracts.errors import ErrorCode
from backend.app.uploads.rejection import UploadRejected


@dataclass(frozen=True)
class NormalisedFilename:
    """A safe display filename and its lowercased extension (without dot)."""

    display: str
    extension: str


def _basename(raw: str) -> str:
    # Treat both separators as path separators, then take the final component.
    unified = raw.replace("\\", "/")
    return unified.rsplit("/", 1)[-1]


def _strip_control_characters(value: str) -> str:
    # Remove any Unicode control/format characters (category starting with "C").
    return "".join(ch for ch in value if not unicodedata.category(ch).startswith("C"))


def normalise_filename(raw: str, *, max_length: int) -> NormalisedFilename:
    """Normalise a client-supplied filename into a safe display name + extension.

    Raises ``UploadRejected`` with ``upload_invalid_filename`` when the result is
    empty, over-length, or contains a NUL byte.
    """

    if "\x00" in raw:
        raise UploadRejected(ErrorCode.UPLOAD_INVALID_FILENAME, "Filename contains a NUL byte.")

    name = _basename(raw)
    name = unicodedata.normalize("NFC", name)
    name = _strip_control_characters(name)
    name = name.strip()

    if not name:
        raise UploadRejected(ErrorCode.UPLOAD_INVALID_FILENAME, "Filename is empty.")
    if len(name) > max_length:
        raise UploadRejected(ErrorCode.UPLOAD_INVALID_FILENAME, "Filename is too long.")

    extension = ""
    if "." in name:
        candidate = name.rsplit(".", 1)[1].lower()
        # Ignore trailing-dot or empty extension.
        if candidate:
            extension = candidate

    return NormalisedFilename(display=name, extension=extension)
