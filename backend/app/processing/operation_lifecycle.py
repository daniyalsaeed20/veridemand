"""Enforceable operation-attempt lifecycle for public progress events.

Coordinator owns public transitions. This ledger prevents duplicate queued/
started/terminal events for the same attempt identity and rejects illegal
regressions (terminal → active under the same attempt).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

_TERMINAL = frozenset({"completed", "failed", "timed_out", "cancelled", "skipped"})


class LifecycleRejectReason(StrEnum):
    DUPLICATE_QUEUED = "duplicate_event_prevented"
    DUPLICATE_STARTED = "duplicate_event_prevented"
    DUPLICATE_TERMINAL = "duplicate_event_prevented"
    INVALID_TRANSITION = "invalid_transition_prevented"
    STALE_ATTEMPT = "stale_event_rejected"


@dataclass(frozen=True, slots=True)
class OperationAttemptId:
    operation_id: str
    document_id: str
    operation: str
    attempt_number: int
    worker_generation: int | None = None
    document_page_number: int | None = None

    def key(self) -> tuple[object, ...]:
        return (
            self.operation_id,
            self.document_id,
            self.document_page_number,
            self.operation,
            self.attempt_number,
            self.worker_generation,
        )


@dataclass
class AttemptRecord:
    attempt: OperationAttemptId
    queued_count: int = 0
    started_count: int = 0
    terminal_count: int = 0
    terminal_status: str | None = None
    heartbeat_count: int = 0


@dataclass
class LifecycleDecision:
    accepted: bool
    reason: LifecycleRejectReason | None = None
    record: AttemptRecord | None = None


@dataclass
class OperationLifecycleLedger:
    """In-memory ledger for one document's public operation attempts."""

    _attempts: dict[tuple[object, ...], AttemptRecord] = field(default_factory=dict)
    _current_key: tuple[object, ...] | None = None

    def get(self, attempt: OperationAttemptId) -> AttemptRecord | None:
        return self._attempts.get(attempt.key())

    def current(self) -> AttemptRecord | None:
        if self._current_key is None:
            return None
        return self._attempts.get(self._current_key)

    def register_queued(self, attempt: OperationAttemptId) -> LifecycleDecision:
        record = self._ensure(attempt)
        if record.queued_count >= 1:
            return LifecycleDecision(False, LifecycleRejectReason.DUPLICATE_QUEUED, record)
        if record.started_count > 0 or record.terminal_count > 0:
            return LifecycleDecision(False, LifecycleRejectReason.INVALID_TRANSITION, record)
        record.queued_count = 1
        self._current_key = attempt.key()
        return LifecycleDecision(True, None, record)

    def register_started(self, attempt: OperationAttemptId) -> LifecycleDecision:
        record = self._ensure(attempt)
        if record.terminal_count > 0:
            return LifecycleDecision(False, LifecycleRejectReason.INVALID_TRANSITION, record)
        if record.started_count >= 1:
            return LifecycleDecision(False, LifecycleRejectReason.DUPLICATE_STARTED, record)
        record.started_count = 1
        self._current_key = attempt.key()
        return LifecycleDecision(True, None, record)

    def register_heartbeat(self, attempt: OperationAttemptId) -> LifecycleDecision:
        record = self._ensure(attempt)
        if record.terminal_count > 0:
            return LifecycleDecision(False, LifecycleRejectReason.INVALID_TRANSITION, record)
        if record.started_count < 1:
            return LifecycleDecision(False, LifecycleRejectReason.INVALID_TRANSITION, record)
        record.heartbeat_count += 1
        return LifecycleDecision(True, None, record)

    def register_terminal(
        self,
        attempt: OperationAttemptId,
        status: str,
        *,
        allow_skip_without_start: bool = False,
    ) -> LifecycleDecision:
        status_value = getattr(status, "value", status)
        if status_value not in _TERMINAL:
            return LifecycleDecision(False, LifecycleRejectReason.INVALID_TRANSITION, None)
        record = self._ensure(attempt)
        if record.terminal_count >= 1:
            return LifecycleDecision(False, LifecycleRejectReason.DUPLICATE_TERMINAL, record)
        if record.started_count < 1 and not (
            allow_skip_without_start and status_value == "skipped"
        ):
            return LifecycleDecision(False, LifecycleRejectReason.INVALID_TRANSITION, record)
        record.terminal_count = 1
        record.terminal_status = str(status_value)
        return LifecycleDecision(True, None, record)

    def is_stale_attempt(
        self,
        attempt: OperationAttemptId,
        *,
        current_attempt_number: int,
        current_page: int | None,
        current_generation: int | None,
    ) -> bool:
        if attempt.attempt_number < current_attempt_number:
            return True
        if (
            current_page is not None
            and attempt.document_page_number is not None
            and attempt.document_page_number != current_page
        ):
            current = self.current()
            if current is not None and current.attempt.document_page_number == current_page:
                return True
        return (
            current_generation is not None
            and attempt.worker_generation is not None
            and attempt.worker_generation < current_generation
        )

    def _ensure(self, attempt: OperationAttemptId) -> AttemptRecord:
        key = attempt.key()
        record = self._attempts.get(key)
        if record is None:
            record = AttemptRecord(attempt=attempt)
            self._attempts[key] = record
        return record
