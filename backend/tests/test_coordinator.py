from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from backend.app.contracts.documents import DocumentStatus
from backend.app.contracts.jobs import JobStatus
from backend.app.processing.admission import AdmissionError
from backend.app.processing.cancellation import CancellationToken
from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.settings.config import Settings

from .conftest import build_coordinator, build_runtime, register_document


async def _wait_for(predicate: Callable[[], bool], max_wait: float = 3.0) -> None:
    async def _run() -> None:
        while not predicate():  # noqa: ASYNC110 - polling external coordinator state in tests
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_run(), max_wait)


class RecordingAdmission:
    def __init__(self) -> None:
        self.order: list[str] = []

    async def prepare(
        self, session: RuntimeSession, document: RuntimeDocument, cancellation: CancellationToken
    ) -> None:
        self.order.append(document.document_id)


class BlockingAdmission:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def prepare(
        self, session: RuntimeSession, document: RuntimeDocument, cancellation: CancellationToken
    ) -> None:
        self.started.set()
        await self.release.wait()
        cancellation.raise_if_cancelled()


class FailingAdmission:
    async def prepare(
        self, session: RuntimeSession, document: RuntimeDocument, cancellation: CancellationToken
    ) -> None:
        raise AdmissionError("boom")


def test_multiple_workers_rejected(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    from backend.app.processing.admission import Phase1AdmissionProcessor

    with pytest.raises(ValueError, match="one admission worker"):
        ProcessingCoordinator(
            registry, queue, Phase1AdmissionProcessor(file_store), file_store, worker_count=2
        )


async def test_happy_path_marks_ready_with_bounded_progress(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(registry, queue, file_store)
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await _wait_for(lambda: document.status is DocumentStatus.READY_FOR_EXTRACTION)
    finally:
        await coordinator.stop()

    summary = document.to_summary()
    assert summary.progress_percent <= 5
    assert summary.result_available is False
    assert summary.extraction_performed is False
    job = next(iter(session.jobs.values()))
    assert job.status is JobStatus.COMPLETED


async def test_fifo_single_worker_order(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    recorder = RecordingAdmission()
    coordinator = build_coordinator(registry, queue, file_store, admission=recorder)
    session = await registry.create()
    docs = [register_document(file_store, session) for _ in range(4)]

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [d.document_id for d in docs])
        await _wait_for(lambda: all(d.status is DocumentStatus.READY_FOR_EXTRACTION for d in docs))
    finally:
        await coordinator.stop()

    assert recorder.order == [d.document_id for d in docs]


async def test_duplicate_enqueue_prevented(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    blocking = BlockingAdmission()
    coordinator = build_coordinator(registry, queue, file_store, admission=blocking)
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        queued_1, ignored_1 = await coordinator.enqueue_documents(session, [document.document_id])
        await blocking.started.wait()
        queued_2, ignored_2 = await coordinator.enqueue_documents(session, [document.document_id])
        blocking.release.set()
        await _wait_for(lambda: document.status is DocumentStatus.READY_FOR_EXTRACTION)
    finally:
        await coordinator.stop()

    assert len(queued_1) == 1 and not ignored_1
    assert not queued_2 and len(ignored_2) == 1


async def test_cancel_queued_document(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    blocking = BlockingAdmission()
    coordinator = build_coordinator(registry, queue, file_store, admission=blocking)
    session = await registry.create()
    first = register_document(file_store, session)
    second = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [first.document_id, second.document_id])
        await blocking.started.wait()  # first is now running/blocked
        # Second is still queued -> cancel it.
        await coordinator.cancel_document(session, second.document_id)
        assert second.status is DocumentStatus.CANCELLED
        blocking.release.set()
        await _wait_for(lambda: first.status is DocumentStatus.READY_FOR_EXTRACTION)
    finally:
        await coordinator.stop()


async def test_cancel_running_document_is_cooperative(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    blocking = BlockingAdmission()
    coordinator = build_coordinator(registry, queue, file_store, admission=blocking)
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await blocking.started.wait()
        assert document.status is DocumentStatus.PREPARING
        await coordinator.cancel_document(session, document.document_id)
        blocking.release.set()
        await _wait_for(lambda: document.status is DocumentStatus.CANCELLED)
    finally:
        await coordinator.stop()

    job = next(iter(session.jobs.values()))
    assert job.status is JobStatus.CANCELLED


async def test_admission_failure_marks_failed(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(registry, queue, file_store, admission=FailingAdmission())
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
    assert job.failure_code == "admission_failed"


async def test_missing_original_file_fails_admission(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(registry, queue, file_store)
    session = await registry.create()
    document = register_document(file_store, session)
    # Simulate a file-removed race by deleting the accepted original.
    file_store.remove_document_files(session.session_id, document.document_id, document.extension)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await _wait_for(lambda: document.status is DocumentStatus.FAILED)
    finally:
        await coordinator.stop()


async def test_graceful_shutdown_leaves_no_worker(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(registry, queue, file_store)
    coordinator.start()
    assert coordinator.running is True
    await coordinator.stop()
    assert coordinator.running is False


async def test_remove_document_after_ready(settings: Settings) -> None:
    registry, queue, file_store = build_runtime(settings)
    coordinator = build_coordinator(registry, queue, file_store)
    session = await registry.create()
    document = register_document(file_store, session)

    coordinator.start()
    try:
        await coordinator.enqueue_documents(session, [document.document_id])
        await _wait_for(lambda: document.status is DocumentStatus.READY_FOR_EXTRACTION)
        await coordinator.remove_document(session, document.document_id)
    finally:
        await coordinator.stop()

    assert document.document_id not in session.documents
    original = file_store.original_path(
        session.session_id, document.document_id, document.extension
    )
    assert not original.exists()
