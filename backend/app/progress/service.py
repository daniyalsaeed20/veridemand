"""SSE serialisation helpers built on the per-session event broker.

Each emitted message carries a stable ``id`` (the event id, enabling
``Last-Event-ID`` replay), an ``event`` name (the event type) and a ``data``
payload that is the JSON of the strict ``ProgressEvent`` model, so the frontend
can validate every message against the generated schema. Heartbeats are handled
as transport-only SSE comment pings by ``EventSourceResponse`` and are never
persisted in replay history.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from backend.app.contracts.progress import ProgressEvent
from backend.app.progress.broker import EventBroker
from backend.app.progress.models import ConnectResult


def format_event(event: ProgressEvent) -> dict[str, str]:
    """Format a progress event as an EventSourceResponse message dict."""

    return {
        "id": event.event_id,
        "event": event.event.value,
        "data": event.model_dump_json(),
    }


async def sse_event_stream(
    broker: EventBroker, connect: ConnectResult
) -> AsyncIterator[dict[str, str]]:
    """Yield replay, optional resync, then live events for a subscriber."""

    for event in connect.replay:
        yield format_event(event)
    if connect.resync_required:
        yield format_event(await broker.build_resync_event())
    async for event in broker.stream(connect.subscriber):
        yield format_event(event)
