"""Unit tests for the Phase 1 non-extractive admission processor.

Covers the ownership/integrity checks and the test-only cooperative hold used by
E2E to exercise cancellation. Admission never performs extraction of any kind.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from backend.app.contracts.documents import DocumentStatus
from backend.app.processing.admission import AdmissionError, Phase1AdmissionProcessor
from backend.app.processing.cancellation import CancellationToken, JobCancelledError
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

from .conftest import build_runtime, register_document


async def test_marks_ready_without_hold(settings: Settings, file_store: FileStore) -> None:
    registry, _queue, _store = build_runtime(settings)
    session = await registry.create()
    document = register_document(file_store, session)
    processor = Phase1AdmissionProcessor(file_store)

    await processor.prepare(session, document, CancellationToken())

    assert document.status is DocumentStatus.READY_FOR_EXTRACTION


async def test_hold_delays_readiness(settings: Settings, file_store: FileStore) -> None:
    registry, _queue, _store = build_runtime(settings)
    session = await registry.create()
    document = register_document(file_store, session)
    processor = Phase1AdmissionProcessor(file_store, test_hold_seconds=0.2)

    start = time.monotonic()
    await processor.prepare(session, document, CancellationToken())
    elapsed = time.monotonic() - start

    assert elapsed >= 0.2
    assert document.status is DocumentStatus.READY_FOR_EXTRACTION


async def test_hold_observes_cancellation(settings: Settings, file_store: FileStore) -> None:
    registry, _queue, _store = build_runtime(settings)
    session = await registry.create()
    document = register_document(file_store, session)
    processor = Phase1AdmissionProcessor(file_store, test_hold_seconds=5.0)
    token = CancellationToken()

    async def _cancel_soon() -> None:
        await asyncio.sleep(0.1)
        token.cancel()

    with pytest.raises(JobCancelledError):
        await asyncio.gather(processor.prepare(session, document, token), _cancel_soon())

    assert document.status is not DocumentStatus.READY_FOR_EXTRACTION


async def test_missing_original_fails(settings: Settings, file_store: FileStore) -> None:
    registry, _queue, _store = build_runtime(settings)
    session = await registry.create()
    document = register_document(file_store, session)
    file_store.original_path(session.session_id, document.document_id, document.extension).unlink()
    processor = Phase1AdmissionProcessor(file_store)

    with pytest.raises(AdmissionError):
        await processor.prepare(session, document, CancellationToken())
