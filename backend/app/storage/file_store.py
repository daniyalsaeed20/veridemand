"""Temporary, session-owned file storage.

Uploads are streamed to ``staging`` in bounded chunks (never fully buffered in
memory), hashed and byte-counted while streaming, then atomically moved into
``originals`` only after validation. Deletion is ordinary filesystem removal with
bounded retries for transient Windows file-lock errors. Local paths are never
returned in contracts, errors, or logs.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from backend.app.storage import paths


class AsyncByteReader(Protocol):
    """Minimal async reader interface (satisfied by Starlette ``UploadFile``)."""

    async def read(self, size: int = ...) -> bytes: ...


class FileStoreError(RuntimeError):
    """Base class for streaming/storage failures."""


class EmptyUploadError(FileStoreError):
    """The uploaded file contained no bytes."""


class FileTooLargeError(FileStoreError):
    """The uploaded file exceeded the single-file byte limit."""


class SessionBytesExceededError(FileStoreError):
    """The upload would exceed the remaining session byte budget."""


@dataclass(frozen=True)
class StagedFile:
    """Result of streaming an upload into staging."""

    path: Path
    size_bytes: int
    sha256: str


class FileStore:
    """Filesystem operations for session-owned temporary storage."""

    def __init__(
        self, temp_root: Path, *, delete_retries: int = 5, delete_delay: float = 0.05
    ) -> None:
        self._temp_root = temp_root
        self._delete_retries = delete_retries
        self._delete_delay = delete_delay

    @property
    def temp_root(self) -> Path:
        return self._temp_root

    def create_session_storage(self, session_id: str) -> Path:
        """Create the session directory tree and return its root."""

        root = paths.session_dir(self._temp_root, session_id)
        for name in paths.SESSION_SUBDIRS:
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    def staging_path(self, session_id: str, document_id: str) -> Path:
        return paths.staging_path(self._temp_root, session_id, document_id)

    def original_path(self, session_id: str, document_id: str, extension: str) -> Path:
        return paths.original_path(self._temp_root, session_id, document_id, extension)

    def canonical_path(self, session_id: str, document_id: str) -> Path:
        return paths.canonical_path(self._temp_root, session_id, document_id)

    def canonical_part_path(self, session_id: str, document_id: str) -> Path:
        return paths.canonical_part_path(self._temp_root, session_id, document_id)

    async def stage_upload(
        self,
        source: AsyncByteReader,
        *,
        session_id: str,
        document_id: str,
        chunk_bytes: int,
        max_single_file_bytes: int,
        remaining_session_bytes: int,
    ) -> StagedFile:
        """Stream an upload into staging, enforcing limits while writing.

        The partial staged file is removed if any limit is exceeded or the upload
        is empty; the corresponding exception is then re-raised.
        """

        dest = self.staging_path(session_id, document_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        size = 0
        try:
            with dest.open("wb") as handle:
                while True:
                    chunk = await source.read(chunk_bytes)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_single_file_bytes:
                        raise FileTooLargeError
                    if size > remaining_session_bytes:
                        raise SessionBytesExceededError
                    hasher.update(chunk)
                    handle.write(chunk)
            if size == 0:
                raise EmptyUploadError
        except BaseException:
            self.remove_file(dest)
            raise
        return StagedFile(path=dest, size_bytes=size, sha256=hasher.hexdigest())

    def commit_original(self, session_id: str, document_id: str, extension: str) -> Path:
        """Atomically move a staged file into ``originals`` and return its path."""

        staged = self.staging_path(session_id, document_id)
        final = self.original_path(session_id, document_id, extension)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, final)
        return final

    def remove_file(self, path: Path) -> None:
        """Best-effort removal of a single file with bounded retries."""

        for attempt in range(self._delete_retries):
            try:
                path.unlink(missing_ok=True)
                return
            except OSError:
                if attempt == self._delete_retries - 1:
                    return
                time.sleep(self._delete_delay)

    def remove_document_files(
        self, session_id: str, document_id: str, extension: str | None
    ) -> None:
        """Remove a document's staged residue and stored original, if present."""

        self.remove_file(self.staging_path(session_id, document_id))
        if extension is not None:
            self.remove_file(self.original_path(session_id, document_id, extension))
        self.remove_file(self.canonical_path(session_id, document_id))
        self.remove_file(self.canonical_part_path(session_id, document_id))

    def remove_session_storage(self, session_id: str) -> None:
        """Recursively remove a session directory after proving it is safe."""

        target = paths.session_dir(self._temp_root, session_id)
        paths.assert_safe_session_dir(self._temp_root, session_id, target)
        if not target.exists():
            return
        for attempt in range(self._delete_retries):
            try:
                shutil.rmtree(target)
                return
            except OSError:
                if attempt == self._delete_retries - 1:
                    return
                time.sleep(self._delete_delay)

    def sweep_abandoned_sessions(self, active_session_ids: set[str]) -> list[str]:
        """Remove session directories with no in-memory owner.

        Applies the same path-safety checks as ordinary deletion and never
        touches unrelated contents of ``TEMP_ROOT``. Returns removed ids.
        Also removes short LibreOffice workspaces under ``<TEMP_ROOT>/lo/``.
        """

        root = paths.sessions_root(self._temp_root)
        if not root.exists():
            removed: list[str] = []
        else:
            removed = []
            for child in root.iterdir():
                name = child.name
                if name in active_session_ids:
                    continue
                try:
                    paths.assert_safe_session_dir(self._temp_root, name, child)
                except paths.UnsafePathError:
                    continue
                if not child.is_dir() or child.is_symlink():
                    continue
                self.remove_session_storage(name)
                removed.append(name)

        lo_root = self._temp_root / "lo"
        if lo_root.is_dir() and not lo_root.is_symlink():
            for attempt in range(self._delete_retries):
                try:
                    shutil.rmtree(lo_root)
                    break
                except OSError:
                    if attempt == self._delete_retries - 1:
                        break
                    time.sleep(self._delete_delay)
        return removed
