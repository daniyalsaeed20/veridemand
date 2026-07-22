"""Staging, atomic publish, and cleanup helpers for canonical PDFs."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.inspection import CanonicalPdfInspectionService
from backend.app.canonical.models import CanonicalisationResult
from backend.app.contracts.canonical import CanonicalisationMethod, CanonicalPageSourceType
from backend.app.contracts.errors import ErrorCode
from backend.app.settings.config import Settings
from backend.app.storage import paths


class CanonicalisationService:
    """Filesystem helpers shared by canonicalisation producers."""

    def __init__(self, settings: Settings, *, temp_root: Path) -> None:
        self._settings = settings
        self._temp_root = temp_root
        self._inspector = CanonicalPdfInspectionService()

    def staging_canonical_dir(self, session_id: str, job_id: str) -> Path:
        directory = paths.staging_canonical_dir(self._temp_root, session_id, job_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def staging_libreoffice_dir(self, session_id: str, job_id: str) -> Path:
        directory = paths.staging_libreoffice_dir(self._temp_root, session_id, job_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def cleanup_staging(self, session_id: str, job_id: str) -> None:
        for builder in (paths.staging_canonical_dir, paths.staging_libreoffice_dir):
            directory = builder(self._temp_root, session_id, job_id)
            if directory.exists():
                shutil.rmtree(directory, ignore_errors=True)

    def publish_atomic(
        self,
        *,
        session_id: str,
        document_id: str,
        staging_pdf: Path,
        method: CanonicalisationMethod,
        source_type: CanonicalPageSourceType,
        warnings: list[str] | None = None,
        libreoffice_version: str | None = None,
        source_frame_index: int | None = None,
        source_pixel_width: int | None = None,
        source_pixel_height: int | None = None,
    ) -> CanonicalisationResult:
        """Verify, hash, and atomically publish a staged PDF into ``canonical/``."""

        part_path = paths.canonical_part_path(self._temp_root, session_id, document_id)
        final_path = paths.canonical_path(self._temp_root, session_id, document_id)
        part_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if part_path.exists():
            part_path.unlink()
        shutil.copy2(staging_pdf, part_path)

        pages = self._inspector.inspect_file(
            part_path,
            source_type=source_type,
            source_frame_index=source_frame_index,
            source_pixel_width=source_pixel_width,
            source_pixel_height=source_pixel_height,
        )
        digest, size_bytes = _sha256_and_size(part_path)
        os.replace(part_path, final_path)
        return CanonicalisationResult(
            pages=pages,
            method=method,
            sha256=digest,
            size_bytes=size_bytes,
            path=final_path,
            libreoffice_version=libreoffice_version,
            warnings=list(warnings or []),
        )

    def link_or_copy(
        self,
        source: Path,
        destination: Path,
        *,
        chunk_bytes: int,
    ) -> None:
        """Hard-link when possible, otherwise copy in bounded chunks."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        try:
            if source.stat().st_dev == destination.parent.stat().st_dev:
                os.link(source, destination)
                return
        except OSError:
            pass
        _chunked_copy(source, destination, chunk_bytes=chunk_bytes)


def _sha256_and_size(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            size += len(chunk)
    if size == 0:
        raise CanonicalisationError(
            ErrorCode.CANONICALISATION_INVALID_PDF,
            "The canonical PDF is empty.",
        )
    return hasher.hexdigest(), size


def _chunked_copy(source: Path, destination: Path, *, chunk_bytes: int) -> None:
    with source.open("rb") as src, destination.open("wb") as dest:
        while True:
            chunk = src.read(chunk_bytes)
            if not chunk:
                break
            dest.write(chunk)
