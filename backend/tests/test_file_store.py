from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.contracts.identifiers import new_document_id, new_session_id
from backend.app.storage.file_store import (
    EmptyUploadError,
    FileStore,
    FileTooLargeError,
    SessionBytesExceededError,
)


class FakeUpload:
    """Minimal async byte reader over an in-memory buffer."""

    def __init__(self, data: bytes) -> None:
        self._buffer = memoryview(data)
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            chunk = self._buffer[self._pos :]
            self._pos = len(self._buffer)
            return bytes(chunk)
        chunk = self._buffer[self._pos : self._pos + size]
        self._pos += len(chunk)
        return bytes(chunk)


def _ids() -> tuple[str, str]:
    return new_session_id(), new_document_id()


async def test_stage_upload_streams_hash_and_size(file_store: FileStore) -> None:
    session_id, document_id = _ids()
    file_store.create_session_storage(session_id)
    payload = b"hello world " * 1000

    staged = await file_store.stage_upload(
        FakeUpload(payload),
        session_id=session_id,
        document_id=document_id,
        chunk_bytes=64,
        max_single_file_bytes=10_000_000,
        remaining_session_bytes=10_000_000,
    )

    assert staged.size_bytes == len(payload)
    assert staged.sha256 == hashlib.sha256(payload).hexdigest()
    assert staged.path.exists()


async def test_stage_upload_rejects_empty(file_store: FileStore) -> None:
    session_id, document_id = _ids()
    file_store.create_session_storage(session_id)
    with pytest.raises(EmptyUploadError):
        await file_store.stage_upload(
            FakeUpload(b""),
            session_id=session_id,
            document_id=document_id,
            chunk_bytes=64,
            max_single_file_bytes=1000,
            remaining_session_bytes=1000,
        )
    assert not file_store.staging_path(session_id, document_id).exists()


async def test_stage_upload_enforces_single_file_limit(file_store: FileStore) -> None:
    session_id, document_id = _ids()
    file_store.create_session_storage(session_id)
    with pytest.raises(FileTooLargeError):
        await file_store.stage_upload(
            FakeUpload(b"x" * 5000),
            session_id=session_id,
            document_id=document_id,
            chunk_bytes=64,
            max_single_file_bytes=1000,
            remaining_session_bytes=1_000_000,
        )
    assert not file_store.staging_path(session_id, document_id).exists()


async def test_stage_upload_enforces_session_budget(file_store: FileStore) -> None:
    session_id, document_id = _ids()
    file_store.create_session_storage(session_id)
    with pytest.raises(SessionBytesExceededError):
        await file_store.stage_upload(
            FakeUpload(b"x" * 5000),
            session_id=session_id,
            document_id=document_id,
            chunk_bytes=64,
            max_single_file_bytes=1_000_000,
            remaining_session_bytes=1000,
        )
    assert not file_store.staging_path(session_id, document_id).exists()


async def test_commit_original_atomic_move(file_store: FileStore) -> None:
    session_id, document_id = _ids()
    file_store.create_session_storage(session_id)
    await file_store.stage_upload(
        FakeUpload(b"content"),
        session_id=session_id,
        document_id=document_id,
        chunk_bytes=64,
        max_single_file_bytes=1000,
        remaining_session_bytes=1000,
    )
    final = file_store.commit_original(session_id, document_id, "txt")
    assert final.exists()
    assert not file_store.staging_path(session_id, document_id).exists()


def test_remove_session_storage_is_safe_and_recursive(file_store: FileStore) -> None:
    session_id = new_session_id()
    root = file_store.create_session_storage(session_id)
    (root / "originals" / "a.txt").write_text("x", encoding="utf-8")
    assert root.exists()
    file_store.remove_session_storage(session_id)
    assert not root.exists()


def test_sweep_abandoned_sessions_removes_unowned(file_store: FileStore) -> None:
    kept = new_session_id()
    abandoned = new_session_id()
    file_store.create_session_storage(kept)
    file_store.create_session_storage(abandoned)

    removed = file_store.sweep_abandoned_sessions({kept})

    assert abandoned in removed
    assert kept not in removed


def test_sweep_ignores_unrelated_directory_names(file_store: FileStore, tmp_path: Path) -> None:
    from backend.app.storage import paths

    sessions_root = paths.sessions_root(file_store.temp_root)
    sessions_root.mkdir(parents=True, exist_ok=True)
    (sessions_root / "not-a-session-id").mkdir()

    removed = file_store.sweep_abandoned_sessions(set())

    assert "not-a-session-id" not in removed
    assert (sessions_root / "not-a-session-id").exists()
