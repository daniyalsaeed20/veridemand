"""Internal models for the per-session SSE event broker."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from backend.app.contracts.progress import ProgressEvent


class BrokerClosedError(RuntimeError):
    """Raised when subscribing to or publishing on a closed broker."""


class Subscriber:
    """A single SSE subscriber with a bounded delivery queue.

    ``signal`` is set when the subscriber must stop (broker closed) or has
    overflowed (fell too far behind and must resynchronise).
    """

    __slots__ = ("closed", "overflow", "queue", "signal")

    def __init__(self, max_queue_size: int) -> None:
        self.queue: asyncio.Queue[ProgressEvent] = asyncio.Queue(maxsize=max_queue_size)
        self.signal = asyncio.Event()
        self.overflow = False
        self.closed = False


@dataclass
class ConnectResult:
    """Outcome of connecting a subscriber to a broker."""

    subscriber: Subscriber
    replay: list[ProgressEvent] = field(default_factory=list)
    resync_required: bool = False
