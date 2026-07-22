"""Session storage paths and resolved-path safety checks.

The original filename is metadata only and is never used as a filesystem path.
Every destructive operation is guarded by resolved-path containment checks so a
crafted identifier can never escape ``<TEMP_ROOT>/sessions/<session_id>``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from backend.app.contracts.identifiers import (
    DOCUMENT_ID_PATTERN,
    JOB_ID_PATTERN,
    SESSION_ID_PATTERN,
)

# Only staging/ and originals/ are used in Phase 1; the rest establish ownership
# boundaries for later phases.
SESSION_SUBDIRS: Final = (
    "staging",
    "originals",
    "canonical",
    "pages",
    "crops",
    "results",
    "exports",
)

_SESSION_ID_RE: Final = re.compile(SESSION_ID_PATTERN)
_DOCUMENT_ID_RE: Final = re.compile(DOCUMENT_ID_PATTERN)
_JOB_ID_RE: Final = re.compile(JOB_ID_PATTERN)
# Safe lowercased extension (letters/digits only), used for on-disk file names.
_SAFE_EXTENSION_RE: Final = re.compile(r"^[a-z0-9]{1,10}$")


class UnsafePathError(RuntimeError):
    """Raised when a path fails containment/safety checks before deletion."""


def _require_session_id(session_id: str) -> str:
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise UnsafePathError("Invalid session identifier.")
    return session_id


def _require_document_id(document_id: str) -> str:
    if not _DOCUMENT_ID_RE.fullmatch(document_id):
        raise UnsafePathError("Invalid document identifier.")
    return document_id


def _require_job_id(job_id: str) -> str:
    if not _JOB_ID_RE.fullmatch(job_id):
        raise UnsafePathError("Invalid job identifier.")
    return job_id


def _require_safe_extension(extension: str) -> str:
    if not _SAFE_EXTENSION_RE.fullmatch(extension):
        raise UnsafePathError("Invalid file extension for storage.")
    return extension


def sessions_root(temp_root: Path) -> Path:
    """Return the ``<TEMP_ROOT>/sessions`` directory (not created here)."""

    return temp_root / "sessions"


def session_dir(temp_root: Path, session_id: str) -> Path:
    """Return the directory owned by a session (validated identifier)."""

    return sessions_root(temp_root) / _require_session_id(session_id)


def staging_path(temp_root: Path, session_id: str, document_id: str) -> Path:
    """Return the staging upload path for a document."""

    return (
        session_dir(temp_root, session_id)
        / "staging"
        / f"{_require_document_id(document_id)}.upload"
    )


def original_path(temp_root: Path, session_id: str, document_id: str, extension: str) -> Path:
    """Return the accepted-original path (``originals/<document_id>.<ext>``)."""

    name = f"{_require_document_id(document_id)}.{_require_safe_extension(extension)}"
    return session_dir(temp_root, session_id) / "originals" / name


def canonical_path(temp_root: Path, session_id: str, document_id: str) -> Path:
    """Return the published canonical PDF path."""

    name = f"{_require_document_id(document_id)}.pdf"
    return session_dir(temp_root, session_id) / "canonical" / name


def canonical_part_path(temp_root: Path, session_id: str, document_id: str) -> Path:
    """Return the in-progress canonical PDF path (``.part`` suffix)."""

    return canonical_path(temp_root, session_id, document_id).with_suffix(".pdf.part")


def staging_canonical_dir(temp_root: Path, session_id: str, job_id: str) -> Path:
    """Return per-job staging for canonical PDF production."""

    return session_dir(temp_root, session_id) / "staging" / "canonical" / _require_job_id(job_id)


def staging_libreoffice_dir(temp_root: Path, session_id: str, job_id: str) -> Path:
    """Return per-job staging for LibreOffice conversion."""

    return session_dir(temp_root, session_id) / "staging" / "libreoffice" / _require_job_id(job_id)


def staging_native_dir(temp_root: Path, session_id: str, job_id: str) -> Path:
    """Return per-job staging for native extraction."""

    return session_dir(temp_root, session_id) / "staging" / "native" / _require_job_id(job_id)


def native_results_dir(temp_root: Path, session_id: str, document_id: str) -> Path:
    """Return published native results directory for a document."""

    return (
        session_dir(temp_root, session_id)
        / "results"
        / "native"
        / _require_document_id(document_id)
    )


def native_results_part_dir(temp_root: Path, session_id: str, document_id: str) -> Path:
    """Return in-progress native results directory (``.part`` suffix)."""

    return native_results_dir(temp_root, session_id, document_id).with_name(
        f"{_require_document_id(document_id)}.part"
    )


def is_contained(root: Path, candidate: Path) -> bool:
    """Return True only when ``candidate`` resolves strictly inside ``root``."""

    try:
        resolved_root = root.resolve(strict=False)
        resolved = candidate.resolve(strict=False)
    except OSError:
        return False
    if resolved == resolved_root:
        return False
    return resolved_root in resolved.parents


def assert_safe_session_dir(temp_root: Path, session_id: str, path: Path) -> None:
    """Prove ``path`` is the deletable directory for ``session_id``.

    Guards against deleting TEMP_ROOT, the sessions parent, an unrelated path, or
    a symlink escaping the root.
    """

    _require_session_id(session_id)
    root = sessions_root(temp_root)
    expected = session_dir(temp_root, session_id)

    resolved_temp = temp_root.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    resolved_expected = expected.resolve(strict=False)
    resolved_path = path.resolve(strict=False)

    if resolved_path in (resolved_temp, resolved_root):
        raise UnsafePathError("Refusing to delete TEMP_ROOT or the sessions root.")
    if resolved_path != resolved_expected:
        raise UnsafePathError("Path does not match the target session directory.")
    if not is_contained(root, expected):
        raise UnsafePathError("Session directory is not contained under the sessions root.")
    if path.exists() and path.is_symlink():
        raise UnsafePathError("Refusing to delete a symlinked session directory.")
