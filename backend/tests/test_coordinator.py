from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.models import CanonicalisationResult
from backend.app.contracts.canonical import (
    CanonicalisationMethod,
    CanonicalPageMetadata,
    CanonicalPageSourceType,
    CanonicalStatus,
)
from backend.app.contracts.documents import DocumentStatus, PageCountStatus
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.jobs import JobStatus
from backend.app.processing.cancellation import CancellationToken
from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.processing.models import ProcessingJob
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

from .conftest import build_coordinator, build_runtime, register_document


async def _wait_for(predicate: Callable[[], bool], max_wait: float = 5.0) -> None:
    async def _run() -> None:
        while not predicate():  # noqa: ASYNC110 - polling external coordinator state in tests
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_run(), max_wait)


def _fake_result(path: Path) -> CanonicalisationResult:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"%PDF-1.4 fake")
    page = CanonicalPageMetadata(
        page_number=1,
        width_points=612.0,
        height_points=792.0,
        intrinsic_rotation=0,
        source_type=CanonicalPageSourceType.TEXT,
    )
    return CanonicalisationResult(
        pages=[page],
        method=CanonicalisationMethod.REPORTLAB_TEXT_PDF,
        sha256="a" * 64,
        size_bytes=path.stat().st_size,
        path=path,
        libreoffice_version=None,
        warnings=[],
    )


def _apply_fake(document: RuntimeDocument, result: CanonicalisationResult) -> None:
    document.canonical_view_available = True
    document.canonical_size_bytes = result.size_bytes
    document.canonical_sha256 = result.sha256
    document.canonical_page_count = len(result.pages)
    document.canonicalisation_method = result.method
    document.canonical_pages = list(result.pages)
    document.canonical_status = CanonicalStatus.READY
    document.canonical_created_at = datetime.now(UTC)
    document.page_count = len(result.pages)
    document.page_count_status = PageCountStatus.KNOWN
    document.progress_percent = 15


class RecordingProcessor:
    def __init__(self, file_store: FileStore) -> None:
        self.order: list[str] = []
        self._file_store = file_store

    async def canonicalise(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        job: ProcessingJob,
        cancellation: CancellationToken,
    ) -> CanonicalisationResult:
        self.order.append(document.document_id)
        path = self._file_store.canonical_path(session.session_id, document.document_id)
        result = _fake_result(path)
        _apply_fake(document, result)
        return result


class BlockingProcessor:
    def __init__(self, file_store: FileStore) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self._file_store = file_store

    async def canonicalise(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        job: ProcessingJob,
        cancellation: CancellationToken,
    ) -> CanonicalisationResult:
        self.started.set()
        await self.release.wait()
        cancellation.raise_if_cancelled()
        path = self._file_store.canonical_path(session.session_id, document.document_id)
        result = _fake_result(path)
        _apply_fake(document, result)
        return result


class FailingProcessor:
    async def canonicalise(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        job: ProcessingJob,
        cancellation: CancellationToken,
    ) -> CanonicalisationResult:
        raise CanonicalisationError(ErrorCode.CANONICALISATION_FAILED, "boom")


def test_multiple_workers_rejected(settings: Settings) -> None:
    from backend.app.extraction.native.service import NativeExtractionService

    registry, queue, file_store = build_runtime(settings)
    processor = RecordingProcessor(file_store)
    with pytest.raises(ValueError, match="one processing worker"):
        ProcessingCoordinator(
            registry,
            queue,
            processor,
            file_store,
            NativeExtractionService(settings),
            worker_count=2,
        )


async def test_happy_path_marks_ready_with_bounded_progress(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(
        registry, queue, file_store, processor=RecordingProcessor(file_store), settings=settings
    )
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await _wait_for(lambda: document.status is DocumentStatus.NATIVE_TRUST_COMPLETE)
    finally:
        await coordinator.stop()

    summary = document.to_summary()
    assert summary.progress_percent <= 35
    assert summary.result_available is False
    assert summary.extraction_performed is False
    job = next(iter(session.jobs.values()))
    assert job.status is JobStatus.COMPLETED


async def test_fifo_single_worker_order(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    recorder = RecordingProcessor(file_store)
    coordinator = build_coordinator(
        registry, queue, file_store, processor=recorder, settings=settings
    )
    session = await registry.create()
    docs = [register_document(file_store, session) for _ in range(4)]

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [d.document_id for d in docs])
        await _wait_for(lambda: all(d.status is DocumentStatus.NATIVE_TRUST_COMPLETE for d in docs))
    finally:
        await coordinator.stop()

    assert recorder.order == [d.document_id for d in docs]


async def test_duplicate_enqueue_prevented(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    blocking = BlockingProcessor(file_store)
    coordinator = build_coordinator(
        registry, queue, file_store, processor=blocking, settings=settings
    )
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        queued_1, ignored_1 = await coordinator.enqueue_documents(session, [document.document_id])
        await blocking.started.wait()
        queued_2, ignored_2 = await coordinator.enqueue_documents(session, [document.document_id])
        blocking.release.set()
        await _wait_for(lambda: document.status is DocumentStatus.NATIVE_TRUST_COMPLETE)
    finally:
        await coordinator.stop()

    assert len(queued_1) == 1 and not ignored_1
    assert not queued_2 and len(ignored_2) == 1


async def test_cancel_queued_document(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    blocking = BlockingProcessor(file_store)
    coordinator = build_coordinator(
        registry, queue, file_store, processor=blocking, settings=settings
    )
    session = await registry.create()
    first = register_document(file_store, session)
    second = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [first.document_id, second.document_id])
        await blocking.started.wait()
        await coordinator.cancel_document(session, second.document_id)
        assert second.status is DocumentStatus.CANCELLED
        blocking.release.set()
        await _wait_for(lambda: first.status is DocumentStatus.NATIVE_TRUST_COMPLETE)
    finally:
        await coordinator.stop()


async def test_cancel_running_document_is_cooperative(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    blocking = BlockingProcessor(file_store)
    coordinator = build_coordinator(
        registry, queue, file_store, processor=blocking, settings=settings
    )
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await blocking.started.wait()
        assert document.status is DocumentStatus.CANONICALISING
        await coordinator.cancel_document(session, document.document_id)
        blocking.release.set()
        await _wait_for(lambda: document.status is DocumentStatus.CANCELLED)
    finally:
        await coordinator.stop()

    job = next(iter(session.jobs.values()))
    assert job.status is JobStatus.CANCELLED


async def test_canonicalisation_failure_marks_failed(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(
        registry, queue, file_store, processor=FailingProcessor(), settings=settings
    )
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await _wait_for(lambda: document.status is DocumentStatus.FAILED)
    finally:
        await coordinator.stop()

    job = next(iter(session.jobs.values()))
    assert job.status is JobStatus.FAILED
    assert job.failure_code == "canonicalisation_failed"


async def test_missing_original_file_fails_canonicalisation(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(registry, queue, file_store, settings=settings)
    session = await registry.create()
    document = register_document(file_store, session)
    file_store.remove_document_files(session.session_id, document.document_id, document.extension)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await _wait_for(lambda: document.status is DocumentStatus.FAILED)
    finally:
        await coordinator.stop()


async def test_graceful_shutdown_leaves_no_worker(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(registry, queue, file_store, settings=settings)
    coordinator.start()
    assert coordinator.running is True
    await coordinator.stop()
    assert coordinator.running is False


async def test_remove_document_after_ready(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(
        registry, queue, file_store, processor=RecordingProcessor(file_store), settings=settings
    )
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await _wait_for(lambda: document.status is DocumentStatus.NATIVE_TRUST_COMPLETE)
        await coordinator.remove_document(session, document.document_id)
    finally:
        await coordinator.stop()

    assert document.document_id not in session.documents
    original = file_store.original_path(
        session.session_id, document.document_id, document.extension
    )
    assert not original.exists()
