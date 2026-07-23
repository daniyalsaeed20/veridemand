"""Phase 4.4 regression: visual transition + terminal summary + page selection."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.identifiers import new_document_id, new_session_id
from backend.app.contracts.native import NativePageDecision, SourceMode, VisualAgreementStatus
from backend.app.contracts.progress import ProgressEventType
from backend.app.contracts.visual import VisualProcessingStatus
from backend.app.extraction.visual.service import (
    VisualOcrService,
    page_needs_visibility_probe,
    page_requires_visual,
)
from backend.app.processing.coordinator import _safe_publish
from backend.app.progress.broker import EventBroker
from backend.app.progress.models import BrokerClosedError
from backend.app.settings.config import Settings


def _native_page(
    *,
    decision: NativePageDecision = NativePageDecision.ACCEPTED,
    source_mode: SourceMode = SourceMode.NATIVE_AUTHORITY,
    visual_processing_required: bool = False,
    visual_agreement_status: VisualAgreementStatus = VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
) -> SimpleNamespace:
    return SimpleNamespace(
        decision=decision,
        source_mode=source_mode,
        trust=SimpleNamespace(
            visual_processing_required=visual_processing_required,
            visual_agreement_status=visual_agreement_status,
        ),
    )


@pytest.mark.asyncio
async def test_broker_accepts_visual_selection_progress_fields() -> None:
    """Root-cause regression: fair-scheduler kwargs must not raise TypeError.

    First bad state: coordinator passed document_pages_total / visual_pages_*
    to EventBroker.publish before the broker accepted those parameters, aborting
    every document immediately after page selection (before OCR inference).
    CI missed this because no test published those optional selection fields.
    """

    broker = EventBroker(new_session_id(), replay_max=100, subscriber_queue_size=100)
    event = await broker.publish(
        ProgressEventType.DOCUMENT_VISUAL_PAGES_SELECTED,
        document_id=new_document_id(),
        job_id=None,
        pages_total=3,
        pages_completed=0,
        document_pages_total=3,
        native_pages_retained=1,
        visual_pages_selected=2,
        visual_pages_completed=0,
        visual_pages_remaining=2,
    )
    assert event.document_pages_total == 3
    assert event.visual_pages_selected == 2
    assert event.native_pages_retained == 1


@pytest.mark.asyncio
async def test_safe_publish_swallows_unexpected_kwargs_style_errors() -> None:
    """Progress telemetry must never abort extraction."""

    class BrokenBroker:
        async def publish(self, event: object, **fields: object) -> None:
            raise TypeError("unexpected keyword argument 'document_pages_total'")

    await _safe_publish(
        BrokenBroker(),  # type: ignore[arg-type]
        ProgressEventType.DOCUMENT_VISUAL_PAGES_SELECTED,
        document_id=new_document_id(),
        document_pages_total=2,
    )


@pytest.mark.asyncio
async def test_safe_publish_swallows_broker_closed() -> None:
    broker = EventBroker(new_session_id(), replay_max=100, subscriber_queue_size=100)
    await broker.close()
    with pytest.raises(BrokerClosedError):
        await broker.publish(ProgressEventType.HEARTBEAT)
    await _safe_publish(broker, ProgressEventType.HEARTBEAT)


def test_page_selection_a_no_pages_require_visual() -> None:
    page = _native_page()
    assert page_requires_visual(page) is False  # type: ignore[arg-type]
    assert page_needs_visibility_probe(page) is True  # type: ignore[arg-type]


def test_page_selection_b_some_pages_require_visual() -> None:
    retained = _native_page()
    selected = _native_page(
        decision=NativePageDecision.REJECTED,
        source_mode=SourceMode.VISUAL_AUTHORITY,
        visual_processing_required=True,
    )
    assert page_requires_visual(retained) is False  # type: ignore[arg-type]
    assert page_requires_visual(selected) is True  # type: ignore[arg-type]


def test_page_selection_c_all_pages_require_visual() -> None:
    pages = [
        _native_page(
            decision=NativePageDecision.ABSENT,
            source_mode=SourceMode.VISUAL_AUTHORITY,
            visual_processing_required=True,
        )
        for _ in range(3)
    ]
    assert all(page_requires_visual(p) for p in pages)  # type: ignore[arg-type]


def test_page_selection_d_visibility_probe_candidate() -> None:
    page = _native_page(
        visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
    )
    assert page_needs_visibility_probe(page) is True  # type: ignore[arg-type]


def test_publish_terminal_failure_summary_no_text(tmp_path: Path) -> None:
    settings = Settings(temp_root=tmp_path)
    service = VisualOcrService(settings, worker_manager=MagicMock())
    session_id = new_session_id()
    document_id = new_document_id()
    summary = service.publish_terminal_failure_summary(
        session_id=session_id,
        document_id=document_id,
        page_count=2,
        error_code=ErrorCode.OCR_RUNTIME_UNAVAILABLE.value,
        canonical_document_available=True,
        native_pages_retained=2,
        pages_selected=2,
        status=VisualProcessingStatus.VISUAL_PROCESSING_PARTIAL,
        user_status_message="The OCR service failed to process this document.",
    )
    loaded = service.load_summary(session_id, document_id)
    assert loaded is not None
    assert loaded.visual_processing_status is VisualProcessingStatus.VISUAL_PROCESSING_PARTIAL
    assert loaded.canonical_document_available is True
    assert loaded.visual_result_available is False
    assert loaded.error_codes == [ErrorCode.OCR_RUNTIME_UNAVAILABLE.value]
    payload = summary.model_dump(mode="json")
    assert "words" not in payload
    assert "lines" not in payload
    assert "provisional_native_text" not in payload
    assert summary.created_at.tzinfo is not None
    assert summary.completed_at is not None
    assert summary.completed_at.tzinfo is UTC or summary.completed_at.utcoffset() is not None


def test_terminal_summary_exists_after_publish(tmp_path: Path) -> None:
    settings = Settings(temp_root=tmp_path)
    service = VisualOcrService(settings, worker_manager=MagicMock())
    session_id = new_session_id()
    document_id = new_document_id()
    service.publish_terminal_failure_summary(
        session_id=session_id,
        document_id=document_id,
        page_count=1,
        error_code="ocr_runtime_unavailable",
        canonical_document_available=True,
    )
    assert service.load_summary(session_id, document_id) is not None
