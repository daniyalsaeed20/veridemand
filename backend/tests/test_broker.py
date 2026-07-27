from __future__ import annotations

import pytest

from backend.app.contracts.identifiers import new_session_id
from backend.app.contracts.progress import ProgressEventType
from backend.app.progress.broker import EventBroker
from backend.app.progress.models import BrokerClosedError


def _broker(replay_max: int = 100, queue_size: int = 100) -> EventBroker:
    return EventBroker(new_session_id(), replay_max=replay_max, subscriber_queue_size=queue_size)


async def test_publish_allocates_increasing_sequence_and_stable_ids() -> None:
    broker = _broker()
    first = await broker.publish(ProgressEventType.SESSION_CREATED)
    second = await broker.publish(ProgressEventType.DOCUMENT_UPLOADED)

    assert first.event_sequence == 1
    assert second.event_sequence == 2
    assert first.event_id == "evt_000000000001"
    assert second.event_id == "evt_000000000002"


async def test_recent_events_returns_oldest_first_bounded() -> None:
    broker = _broker(replay_max=3)
    for _ in range(5):
        await broker.publish(ProgressEventType.HEARTBEAT)
    recent = broker.recent_events(10)
    assert len(recent) == 3
    sequences = [event.event_sequence for event in recent]
    assert sequences == sorted(sequences)
    assert sequences[0] == 3


async def test_connect_without_last_event_id_gets_no_replay() -> None:
    broker = _broker()
    await broker.publish(ProgressEventType.SESSION_CREATED)
    result = await broker.connect(None)
    assert result.replay == []
    assert result.resync_required is False


async def test_connect_replays_events_after_last_event_id() -> None:
    broker = _broker()
    await broker.publish(ProgressEventType.SESSION_CREATED)  # seq 1
    await broker.publish(ProgressEventType.DOCUMENT_UPLOADED)  # seq 2
    await broker.publish(ProgressEventType.DOCUMENT_QUEUED)  # seq 3

    result = await broker.connect("evt_000000000001")
    replayed = [event.event_sequence for event in result.replay]
    assert replayed == [2, 3]
    assert result.resync_required is False


async def test_connect_requires_resync_when_history_truncated() -> None:
    broker = _broker(replay_max=2)
    for _ in range(5):
        await broker.publish(ProgressEventType.HEARTBEAT)
    # Requesting an id older than the retained window forces a resync.
    result = await broker.connect("evt_000000000001")
    assert result.resync_required is True


async def test_connect_malformed_last_event_id_forces_resync() -> None:
    broker = _broker()
    await broker.publish(ProgressEventType.SESSION_CREATED)
    result = await broker.connect("not-a-valid-id")
    assert result.resync_required is True


async def test_slow_subscriber_overflow_signals_resync() -> None:
    broker = _broker(queue_size=1)
    connect = await broker.connect(None)
    # Publish more than the subscriber queue can hold without draining.
    await broker.publish(ProgressEventType.HEARTBEAT)
    await broker.publish(ProgressEventType.HEARTBEAT)
    await broker.publish(ProgressEventType.HEARTBEAT)

    assert connect.subscriber.overflow is True

    stream = broker.stream(connect.subscriber)
    event = await anext(stream)
    assert event.event is ProgressEventType.STREAM_RESYNC_REQUIRED


async def test_publish_after_close_raises() -> None:
    broker = _broker()
    await broker.close()
    assert broker.closed is True
    with pytest.raises(BrokerClosedError):
        await broker.publish(ProgressEventType.HEARTBEAT)


async def test_format_event_shape_for_sse() -> None:
    from backend.app.contracts.progress import ProgressEvent
    from backend.app.progress.service import format_event

    broker = _broker()
    event = await broker.publish(ProgressEventType.DOCUMENT_UPLOADED)
    message = format_event(event)

    assert message["id"] == event.event_id
    assert message["event"] == "document.uploaded"
    # The data payload is the strict ProgressEvent JSON, re-parseable by clients.
    ProgressEvent.model_validate_json(message["data"])


async def test_stream_drains_buffered_events_after_close() -> None:
    broker = _broker()
    connect = await broker.connect(None)
    await broker.publish(ProgressEventType.SESSION_DELETED)
    await broker.close()

    events = [event async for event in broker.stream(connect.subscriber)]
    assert any(e.event is ProgressEventType.SESSION_DELETED for e in events)


async def test_publish_accepts_phase45_route_and_eta_fields() -> None:
    """Regression: Phase 4.5 kwargs must not TypeError on EventBroker.publish."""

    broker = _broker()
    event = await broker.publish(
        ProgressEventType.DOCUMENT_PAGE_ROUTE_COMPLETED,
        document_id="doc_0123456789abcdef0123456789abcdef",
        page_number=1,
        progress_version=3,
        current_route="full_visual_ocr",
        estimate_status="collecting_samples",
        estimate_sample_count=2,
        estimated_document_remaining_seconds=120.0,
        estimated_document_seconds_remaining=120.0,
        embedded_ocr_pages_verified=4,
        full_ocr_pages_selected=10,
        full_ocr_pages_completed=1,
        full_ocr_pages_remaining=9,
        average_full_ocr_page_seconds=25.0,
        fair_scheduling_enabled=False,
        unknown_should_be_ignored="nope",  # type: ignore[call-arg]
    )
    assert event.progress_version == 3
    assert event.current_route == "full_visual_ocr"
    assert event.full_ocr_pages_remaining == 9
    assert event.estimate_status == "collecting_samples"

