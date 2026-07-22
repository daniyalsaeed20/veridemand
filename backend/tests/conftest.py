from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.canonical.processor import DefaultCanonicalisationProcessor
from backend.app.contracts.documents import (
    DocumentFormat,
    DocumentStatus,
    PageCountStatus,
)
from backend.app.contracts.identifiers import new_document_id
from backend.app.main import create_app
from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.processing.queue import InMemoryJobQueue
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.sessions.registry import SessionRegistry
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "synthetic" / "uploads"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointed at an isolated, writable temporary workspace."""

    return Settings(temp_root=tmp_path / "temp")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def uploads_dir() -> Path:
    return _FIXTURES_ROOT


@pytest.fixture(scope="session")
def upload_manifest() -> list[dict[str, object]]:
    data = json.loads((_FIXTURES_ROOT / "MANIFEST.json").read_text(encoding="utf-8"))
    return list(data["fixtures"])


@pytest.fixture
def file_store(settings: Settings) -> FileStore:
    return FileStore(settings.temp_root)


def register_document(
    file_store: FileStore,
    session: RuntimeSession,
    *,
    content: bytes = b"synthetic-original-bytes",
    extension: str = "txt",
    fmt: DocumentFormat = DocumentFormat.TXT,
    page_count: int | None = None,
    page_count_status: PageCountStatus = PageCountStatus.PENDING_CANONICALISATION,
) -> RuntimeDocument:
    """Write a real original file and register an accepted document on a session."""

    document_id = new_document_id()
    original = file_store.original_path(session.session_id, document_id, extension)
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(content)

    document = RuntimeDocument(
        document_id=document_id,
        display_filename=f"{document_id}.{extension}",
        extension=extension,
        format=fmt,
        media_type="text/plain",
        size_bytes=len(content),
        sha256="0" * 64,
        page_count=page_count,
        page_count_status=page_count_status,
        status=DocumentStatus.UPLOADED,
        text_encoding="utf-8" if fmt is DocumentFormat.TXT else None,
    )
    session.documents[document_id] = document
    session.accepted_bytes += len(content)
    if page_count is not None:
        session.known_pages += page_count
    return document


def build_runtime(settings: Settings) -> tuple[SessionRegistry, InMemoryJobQueue, FileStore]:
    """Construct a registry/queue/file-store trio for coordinator-level tests."""

    file_store = FileStore(settings.temp_root)
    job_queue = InMemoryJobQueue()
    registry = SessionRegistry(settings, file_store, job_queue)
    return registry, job_queue, file_store


def build_coordinator(
    registry: SessionRegistry,
    job_queue: InMemoryJobQueue,
    file_store: FileStore,
    processor: object | None = None,
    *,
    settings: Settings | None = None,
) -> ProcessingCoordinator:
    resolved_settings = settings or Settings(temp_root=file_store.temp_root)
    resolved = processor or DefaultCanonicalisationProcessor(resolved_settings, file_store)
    return ProcessingCoordinator(
        registry,
        job_queue,
        resolved,  # type: ignore[arg-type]
        file_store,
        max_pages_per_session=resolved_settings.max_pages_per_session,
    )
