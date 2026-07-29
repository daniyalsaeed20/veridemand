"""Deterministic fair document scheduler (Correction 7).

Implements weighted round-robin across documents with pending heavy OCR work.
Native-only and cheap work bypass this scheduler entirely.

Heavy OCR work is admitted as one work unit per selected page. The coordinator's
heavy consumer claims a unit per turn, so quantum, priority, and yield decisions
made here directly control which document's page runs next.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.app.contracts.scheduling import (
    PriorityClass,
    SchedulingDocumentState,
    WorkClass,
    WorkUnitStatus,
)

_TERMINAL_STATES = frozenset(
    {
        SchedulingDocumentState.CANCELLED,
        SchedulingDocumentState.COMPLETED,
        SchedulingDocumentState.FAILED,
    }
)

_VALID_TRANSITIONS: dict[SchedulingDocumentState, frozenset[SchedulingDocumentState]] = {
    SchedulingDocumentState.NOT_ADMITTED: frozenset({SchedulingDocumentState.READY}),
    SchedulingDocumentState.READY: frozenset(
        {
            SchedulingDocumentState.RUNNING,
            SchedulingDocumentState.CANCELLING,
            SchedulingDocumentState.COMPLETED,
            SchedulingDocumentState.FAILED,
        }
    ),
    SchedulingDocumentState.RUNNING: frozenset(
        {
            SchedulingDocumentState.CHECKPOINTED,
            SchedulingDocumentState.COMPLETED,
            SchedulingDocumentState.FAILED,
            SchedulingDocumentState.CANCELLING,
        }
    ),
    SchedulingDocumentState.YIELDING: frozenset(
        {
            SchedulingDocumentState.CHECKPOINTED,
        }
    ),
    SchedulingDocumentState.CHECKPOINTED: frozenset(
        {
            SchedulingDocumentState.READY,
            SchedulingDocumentState.CANCELLING,
            SchedulingDocumentState.COMPLETED,
        }
    ),
    SchedulingDocumentState.BLOCKED: frozenset(
        {
            SchedulingDocumentState.READY,
            SchedulingDocumentState.CANCELLING,
        }
    ),
    SchedulingDocumentState.CANCELLING: frozenset(
        {
            SchedulingDocumentState.CANCELLED,
        }
    ),
    SchedulingDocumentState.CANCELLED: frozenset(),
    SchedulingDocumentState.COMPLETED: frozenset(),
    SchedulingDocumentState.FAILED: frozenset(),
}


def _new_work_unit_id() -> str:
    return f"wu_{uuid.uuid4().hex}"


@dataclass(slots=True)
class SchedulerWorkUnit:
    work_unit_id: str
    session_id: str
    document_id: str
    route: str
    work_class: WorkClass
    document_page_number: int
    document_pages_total: int
    selected_page_index: int
    selected_pages_total: int
    repair_region_start_index: int | None = None
    repair_region_end_index: int | None = None
    priority_class: PriorityClass = PriorityClass.NORMAL
    priority_value: int = 0
    admitted_sequence: int = 0
    document_turn_sequence: int = 0
    work_unit_sequence: int = 0
    attempt_number: int = 1
    worker_generation: int | None = None
    estimated_cost_class: str | None = None
    estimated_duration_seconds: float | None = None
    status: WorkUnitStatus = WorkUnitStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    checkpoint_version: int = 0
    policy_version: str = "correction7-v1"


@dataclass(slots=True)
class DocumentCheckpoint:
    """Resumable heavy-page state for one document. Never holds page text."""

    document_id: str
    last_terminal_page: int | None = None
    remaining_work_units: int = 0
    checkpoint_version: int = 0
    scheduler_turn: int = 0
    safe_resume_state: str = "checkpointed"
    route_policy_version: str = ""
    completed_pages: set[int] = field(default_factory=set)
    selected_heavy_pages: set[int] = field(default_factory=set)
    failed_heavy_pages: set[int] = field(default_factory=set)
    remaining_heavy_pages: set[int] = field(default_factory=set)
    current_quantum: int = 0
    turn_number: int = 0
    summary_pending: bool = False
    reconciliation_pending: bool = False

    @property
    def completed_heavy_pages(self) -> set[int]:
        """Alias of ``completed_pages`` under the Correction 7 vocabulary."""

        return self.completed_pages

    def mark_completed(self, page_number: int) -> None:
        self.completed_pages.add(page_number)
        self.failed_heavy_pages.discard(page_number)
        self.remaining_heavy_pages.discard(page_number)

    def mark_failed(self, page_number: int) -> None:
        self.failed_heavy_pages.add(page_number)
        self.remaining_heavy_pages.discard(page_number)

    def clear(self) -> None:
        """Drop all resumable state once the document reaches a terminal state."""

        self.completed_pages.clear()
        self.selected_heavy_pages.clear()
        self.failed_heavy_pages.clear()
        self.remaining_heavy_pages.clear()
        self.remaining_work_units = 0
        self.current_quantum = 0
        self.summary_pending = False
        self.reconciliation_pending = False
        self.safe_resume_state = "cleared"


@dataclass(slots=True)
class ScheduledDocument:
    document_id: str
    session_id: str
    state: SchedulingDocumentState = SchedulingDocumentState.NOT_ADMITTED
    priority_class: PriorityClass = PriorityClass.NORMAL
    base_priority_value: int = 0
    effective_priority: int = 0
    aging_adjustment: int = 0
    turn_number: int = 0
    turns_completed: int = 0
    turns_skipped: int = 0
    consecutive_turns: int = 0
    waiting_since: float | None = None
    last_turn_at: datetime | None = None
    admitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    admitted_sequence: int = 0
    work_units: deque[SchedulerWorkUnit] = field(default_factory=deque)
    completed_units: list[SchedulerWorkUnit] = field(default_factory=list)
    checkpoint: DocumentCheckpoint | None = None
    total_heavy_pages: int = 0
    next_eligible_turn: int = 0
    quantum_completed: int = 0

    @property
    def remaining_work(self) -> int:
        return len(self.work_units)

    @property
    def waiting_seconds(self) -> float:
        if self.waiting_since is None:
            return 0.0
        return max(0.0, time.monotonic() - self.waiting_since)

    def transition_to(self, new_state: SchedulingDocumentState) -> None:
        valid = _VALID_TRANSITIONS.get(self.state, frozenset())
        if new_state not in valid:
            raise InvalidTransitionError(
                f"Cannot transition from {self.state.value} to {new_state.value} "
                f"for document {self.document_id}"
            )
        if new_state == SchedulingDocumentState.READY and self.waiting_since is None:
            self.waiting_since = time.monotonic()
        elif new_state == SchedulingDocumentState.RUNNING:
            self.waiting_since = None
        self.state = new_state


class InvalidTransitionError(ValueError):
    pass


# Priority ordering for class-based comparison (lower = higher priority).
_PRIORITY_CLASS_ORDER = {
    PriorityClass.INTERACTIVE_SHORT: 0,
    PriorityClass.NORMAL: 1,
    PriorityClass.LARGE_BACKGROUND: 2,
}


def classify_priority(heavy_page_count: int, *, short_threshold: int = 3) -> PriorityClass:
    if heavy_page_count <= short_threshold:
        return PriorityClass.INTERACTIVE_SHORT
    elif heavy_page_count <= 20:
        return PriorityClass.NORMAL
    return PriorityClass.LARGE_BACKGROUND


@dataclass
class SchedulerConfig:
    enabled: bool = True
    page_quantum: int = 2
    repair_page_quantum: int = 2
    short_document_heavy_page_threshold: int = 3
    aging_enabled: bool = True
    aging_interval_seconds: float = 30.0
    max_consecutive_turns: int = 4
    policy_version: str = "correction7-v1"


class FairDocumentScheduler:
    """Deterministic weighted round-robin scheduler across documents."""

    def __init__(self, config: SchedulerConfig | None = None) -> None:
        self._config = config or SchedulerConfig()
        self._documents: dict[str, ScheduledDocument] = {}
        self._ready_by_class: dict[PriorityClass, deque[str]] = {
            pc: deque() for pc in PriorityClass
        }
        self._active_document_id: str | None = None
        self._active_work_unit: SchedulerWorkUnit | None = None
        self._turn_number: int = 0
        self._admitted_counter: int = 0
        self._checkpoint_counter: int = 0
        self._history: deque[dict[str, Any]] = deque(maxlen=256)
        self._closed: bool = False

    @property
    def config(self) -> SchedulerConfig:
        return self._config

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def turn_number(self) -> int:
        return self._turn_number

    @property
    def active_document_id(self) -> str | None:
        return self._active_document_id

    @property
    def active_work_unit(self) -> SchedulerWorkUnit | None:
        return self._active_work_unit

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        self._closed = True
        self._active_work_unit = None
        self._active_document_id = None
        for queue in self._ready_by_class.values():
            queue.clear()
        for doc in self._documents.values():
            if doc.checkpoint is not None:
                doc.checkpoint.clear()
            doc.work_units.clear()
        self._record_event("scheduler_closed")

    def admit_document(
        self,
        document_id: str,
        session_id: str,
        work_units: list[SchedulerWorkUnit],
    ) -> ScheduledDocument:
        if self._closed:
            raise RuntimeError("Scheduler is closed")
        if document_id in self._documents:
            raise ValueError(f"Document {document_id} already admitted")

        self._admitted_counter += 1
        heavy_count = sum(
            1
            for u in work_units
            if u.work_class in (WorkClass.FULL_OCR_PAGE, WorkClass.TARGETED_REPAIR_PAGE)
        )
        priority_class = classify_priority(
            heavy_count,
            short_threshold=self._config.short_document_heavy_page_threshold,
        )
        doc = ScheduledDocument(
            document_id=document_id,
            session_id=session_id,
            priority_class=priority_class,
            base_priority_value=_PRIORITY_CLASS_ORDER[priority_class],
            effective_priority=_PRIORITY_CLASS_ORDER[priority_class],
            admitted_sequence=self._admitted_counter,
            total_heavy_pages=heavy_count,
        )
        heavy_pages: set[int] = set()
        for i, unit in enumerate(work_units, 1):
            unit.admitted_sequence = self._admitted_counter
            unit.work_unit_sequence = i
            unit.priority_class = priority_class
            unit.priority_value = doc.effective_priority
            unit.policy_version = self._config.policy_version
            doc.work_units.append(unit)
            if unit.work_class in (WorkClass.FULL_OCR_PAGE, WorkClass.TARGETED_REPAIR_PAGE):
                heavy_pages.add(unit.document_page_number)
        doc.checkpoint = DocumentCheckpoint(
            document_id=document_id,
            remaining_work_units=len(doc.work_units),
            route_policy_version=self._config.policy_version,
            selected_heavy_pages=set(heavy_pages),
            remaining_heavy_pages=set(heavy_pages),
            safe_resume_state="admitted",
        )
        doc.transition_to(SchedulingDocumentState.READY)
        self._documents[document_id] = doc
        self._ready_by_class[priority_class].append(document_id)
        self._record_event(
            "document_admitted",
            document_id=document_id,
            priority_class=priority_class.value,
            heavy_pages=heavy_count,
        )
        return doc

    def cancel_document(self, document_id: str) -> ScheduledDocument | None:
        doc = self._documents.get(document_id)
        if doc is None:
            return None
        if doc.state in _TERMINAL_STATES:
            return doc
        if doc.state in (
            SchedulingDocumentState.RUNNING,
            SchedulingDocumentState.READY,
            SchedulingDocumentState.CHECKPOINTED,
            SchedulingDocumentState.BLOCKED,
            SchedulingDocumentState.NOT_ADMITTED,
            SchedulingDocumentState.YIELDING,
        ):
            doc.transition_to(SchedulingDocumentState.CANCELLING)
        for unit in doc.work_units:
            if unit.status in (WorkUnitStatus.PENDING, WorkUnitStatus.RETRYING):
                unit.status = WorkUnitStatus.CANCELLED
        doc.transition_to(SchedulingDocumentState.CANCELLED)
        doc.work_units.clear()
        self.cleanup_checkpoint(doc)
        self._remove_from_ready(document_id, doc.priority_class)
        if self._active_document_id == document_id:
            self._active_document_id = None
            self._active_work_unit = None
        self._record_event("document_cancelled", document_id=document_id)
        return doc

    def complete_document(self, document_id: str) -> ScheduledDocument | None:
        doc = self._documents.get(document_id)
        if doc is None:
            return None
        if doc.state in _TERMINAL_STATES:
            return doc
        doc.transition_to(SchedulingDocumentState.COMPLETED)
        self.cleanup_checkpoint(doc)
        self._remove_from_ready(document_id, doc.priority_class)
        if self._active_document_id == document_id:
            self._active_document_id = None
            self._active_work_unit = None
        self._record_event("document_completed", document_id=document_id)
        return doc

    def fail_document(self, document_id: str) -> ScheduledDocument | None:
        doc = self._documents.get(document_id)
        if doc is None:
            return None
        if doc.state in _TERMINAL_STATES:
            return doc
        doc.transition_to(SchedulingDocumentState.FAILED)
        self._remove_from_ready(document_id, doc.priority_class)
        if self._active_document_id == document_id:
            self._active_document_id = None
            self._active_work_unit = None
        self._record_event("document_failed", document_id=document_id)
        return doc

    def next_work_unit(self) -> tuple[ScheduledDocument, SchedulerWorkUnit] | None:
        if self._closed:
            return None
        self._apply_aging()
        doc = None
        if self._active_document_id is not None:
            current = self._documents.get(self._active_document_id)
            if (
                current is not None
                and current.state == SchedulingDocumentState.RUNNING
                and current.remaining_work > 0
                and current.quantum_completed < self._quantum_for(current)
            ):
                doc = current
            else:
                self._active_document_id = None
                self._active_work_unit = None
                if (
                    current is not None
                    and current.state == SchedulingDocumentState.RUNNING
                    and current.remaining_work > 0
                ):
                    current.transition_to(SchedulingDocumentState.CHECKPOINTED)
                    current.transition_to(SchedulingDocumentState.READY)
                    self._ready_by_class[current.priority_class].append(current.document_id)
                    current.consecutive_turns = 0
                    current.quantum_completed = 0
        if doc is None:
            doc = self._select_next_document()
        if doc is None:
            return None
        if doc.remaining_work == 0:
            return None
        unit = doc.work_units[0]
        self._turn_number += 1
        doc.turn_number = self._turn_number
        doc.turns_completed += 1
        doc.last_turn_at = datetime.now(UTC)
        if doc.quantum_completed == 0:
            doc.consecutive_turns += 1
        unit.document_turn_sequence = doc.turns_completed
        unit.status = WorkUnitStatus.RUNNING
        unit.started_at = datetime.now(UTC)
        if doc.state != SchedulingDocumentState.RUNNING:
            doc.transition_to(SchedulingDocumentState.RUNNING)
        self._active_document_id = doc.document_id
        self._active_work_unit = unit
        for other_id, other_doc in self._documents.items():
            if other_id != doc.document_id and other_doc.state == SchedulingDocumentState.READY:
                other_doc.turns_skipped += 1
        self._record_event(
            "turn_started",
            document_id=doc.document_id,
            work_unit_id=unit.work_unit_id,
            turn=self._turn_number,
        )
        return doc, unit

    def complete_work_unit(self, work_unit_id: str) -> SchedulerWorkUnit | None:
        doc, unit = self._find_unit(work_unit_id)
        if doc is None or unit is None:
            return None
        unit.status = WorkUnitStatus.COMPLETED
        unit.completed_at = datetime.now(UTC)
        if unit in doc.work_units:
            doc.work_units.remove(unit)
        doc.completed_units.append(unit)
        checkpoint = self._ensure_checkpoint(doc)
        checkpoint.last_terminal_page = unit.document_page_number
        checkpoint.mark_completed(unit.document_page_number)
        checkpoint.remaining_work_units = len(doc.work_units)
        self._checkpoint_counter += 1
        checkpoint.checkpoint_version = self._checkpoint_counter
        checkpoint.scheduler_turn = self._turn_number
        checkpoint.turn_number = self._turn_number
        checkpoint.safe_resume_state = "checkpointed"
        if self._active_work_unit and self._active_work_unit.work_unit_id == work_unit_id:
            self._active_work_unit = None
        doc.quantum_completed += 1
        checkpoint.current_quantum = doc.quantum_completed
        if doc.remaining_work == 0:
            self._active_document_id = None
            self._active_work_unit = None
            if doc.state == SchedulingDocumentState.RUNNING:
                doc.transition_to(SchedulingDocumentState.COMPLETED)
                checkpoint.clear()
        elif self.should_yield(doc.document_id):
            self.yield_document(doc.document_id)
        self._record_event(
            "work_unit_completed",
            document_id=doc.document_id,
            work_unit_id=work_unit_id,
            page=unit.document_page_number,
        )
        return unit

    def fail_work_unit(
        self, work_unit_id: str, *, retryable: bool = False
    ) -> SchedulerWorkUnit | None:
        doc, unit = self._find_unit(work_unit_id)
        if doc is None or unit is None:
            return None
        if retryable and unit.attempt_number < 2:
            unit.status = WorkUnitStatus.RETRYING
            unit.attempt_number += 1
            unit.started_at = None
            unit.completed_at = None
            unit.work_unit_id = _new_work_unit_id()
        else:
            unit.status = WorkUnitStatus.FAILED
            unit.completed_at = datetime.now(UTC)
            if unit in doc.work_units:
                doc.work_units.remove(unit)
            doc.completed_units.append(unit)
            checkpoint = self._ensure_checkpoint(doc)
            checkpoint.last_terminal_page = unit.document_page_number
            checkpoint.mark_failed(unit.document_page_number)
            checkpoint.remaining_work_units = len(doc.work_units)
        if self._active_work_unit and self._active_work_unit.work_unit_id == work_unit_id:
            self._active_work_unit = None
        self._record_event(
            "work_unit_failed",
            document_id=doc.document_id,
            work_unit_id=work_unit_id,
            retryable=retryable,
        )
        return unit

    def should_yield(self, document_id: str) -> bool:
        if not self._config.enabled:
            return False
        doc = self._documents.get(document_id)
        if doc is None:
            return False
        if doc.remaining_work <= 1:
            return False
        quantum = self._quantum_for(doc)
        completed_this_turn = doc.quantum_completed
        if completed_this_turn >= quantum:
            if doc.consecutive_turns >= self._config.max_consecutive_turns:
                return True
            if self._has_other_ready():
                return True
        return False

    def yield_document(self, document_id: str) -> ScheduledDocument | None:
        doc = self._documents.get(document_id)
        if doc is None:
            return None
        if doc.state == SchedulingDocumentState.RUNNING:
            doc.transition_to(SchedulingDocumentState.CHECKPOINTED)
        elif doc.state == SchedulingDocumentState.CHECKPOINTED:
            pass
        else:
            return doc
        doc.consecutive_turns = 0
        doc.quantum_completed = 0
        if doc.checkpoint is not None:
            doc.checkpoint.current_quantum = 0
            doc.checkpoint.safe_resume_state = "checkpointed"
        doc.transition_to(SchedulingDocumentState.READY)
        self._ready_by_class[doc.priority_class].append(document_id)
        if self._active_document_id == document_id:
            self._active_document_id = None
            self._active_work_unit = None
        self._record_event(
            "document_yielded",
            document_id=document_id,
            remaining=doc.remaining_work,
            turn=self._turn_number,
        )
        return doc

    def resume_document(self, document_id: str) -> ScheduledDocument | None:
        doc = self._documents.get(document_id)
        if doc is None:
            return None
        if doc.state == SchedulingDocumentState.CHECKPOINTED:
            doc.transition_to(SchedulingDocumentState.READY)
            self._ready_by_class[doc.priority_class].append(document_id)
        return doc

    def move_ahead(self, document_id: str) -> bool:
        doc = self._documents.get(document_id)
        if doc is None or doc.state in _TERMINAL_STATES:
            return False
        queue = self._ready_by_class[doc.priority_class]
        if document_id not in queue:
            return False
        items = [item for item in queue if item != document_id]
        items.insert(0, document_id)
        if list(queue) == items:
            return False
        queue.clear()
        queue.extend(items)
        self._record_event("priority_moved_ahead", document_id=document_id)
        return True

    def move_behind(self, document_id: str) -> bool:
        doc = self._documents.get(document_id)
        if doc is None or doc.state in _TERMINAL_STATES:
            return False
        queue = self._ready_by_class[doc.priority_class]
        if document_id not in queue:
            return False
        items = list(queue)
        idx = items.index(document_id)
        if idx == len(items) - 1:
            return False
        items[idx], items[idx + 1] = items[idx + 1], items[idx]
        queue.clear()
        queue.extend(items)
        self._record_event("priority_moved_behind", document_id=document_id)
        return True

    def restore_default_priority(self, document_id: str) -> bool:
        doc = self._documents.get(document_id)
        if doc is None or doc.state in _TERMINAL_STATES:
            return False
        doc.aging_adjustment = 0
        doc.effective_priority = doc.base_priority_value
        return True

    def get_document(self, document_id: str) -> ScheduledDocument | None:
        return self._documents.get(document_id)

    def has_work(self) -> bool:
        return any(
            doc.remaining_work > 0
            for doc in self._documents.values()
            if doc.state not in _TERMINAL_STATES
        )

    def ready_count(self) -> int:
        return sum(len(q) for q in self._ready_by_class.values())

    def checkpointed_count(self) -> int:
        return sum(
            1 for d in self._documents.values() if d.state == SchedulingDocumentState.CHECKPOINTED
        )

    def remove_document(self, document_id: str) -> None:
        doc = self._documents.pop(document_id, None)
        if doc is not None:
            self.cleanup_checkpoint(doc)
            self._remove_from_ready(document_id, doc.priority_class)
            if self._active_document_id == document_id:
                self._active_document_id = None
                self._active_work_unit = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "scheduler_enabled": self._config.enabled,
            "scheduler_policy_version": self._config.policy_version,
            "active_document_id": self._active_document_id,
            "active_work_unit_id": (
                self._active_work_unit.work_unit_id if self._active_work_unit else None
            ),
            "ready_document_count": self.ready_count(),
            "checkpointed_document_count": self.checkpointed_count(),
            "turn_number": self._turn_number,
        }

    # --- internal ---

    def _ensure_checkpoint(self, doc: ScheduledDocument) -> DocumentCheckpoint:
        if doc.checkpoint is None:
            doc.checkpoint = DocumentCheckpoint(
                document_id=doc.document_id,
                route_policy_version=self._config.policy_version,
            )
        return doc.checkpoint

    @staticmethod
    def cleanup_checkpoint(doc: ScheduledDocument | None) -> None:
        """Release resumable state; safe to call more than once."""

        if doc is not None and doc.checkpoint is not None:
            doc.checkpoint.clear()

    def _select_next_document(self) -> ScheduledDocument | None:
        for priority_class in (
            PriorityClass.INTERACTIVE_SHORT,
            PriorityClass.NORMAL,
            PriorityClass.LARGE_BACKGROUND,
        ):
            queue = self._ready_by_class[priority_class]
            while queue:
                doc_id = queue[0]
                doc = self._documents.get(doc_id)
                if doc is None or doc.state in _TERMINAL_STATES or doc.remaining_work == 0:
                    queue.popleft()
                    continue
                if doc.state != SchedulingDocumentState.READY:
                    queue.popleft()
                    continue
                queue.popleft()
                return doc
        return None

    def _quantum_for(self, doc: ScheduledDocument) -> int:
        has_repair = any(u.work_class == WorkClass.TARGETED_REPAIR_PAGE for u in doc.work_units)
        if has_repair:
            return self._config.repair_page_quantum
        return self._config.page_quantum

    def _has_other_ready(self) -> bool:
        for queue in self._ready_by_class.values():
            for doc_id in queue:
                doc = self._documents.get(doc_id)
                if (
                    doc is not None
                    and doc.state == SchedulingDocumentState.READY
                    and doc.remaining_work > 0
                    and doc.document_id != self._active_document_id
                ):
                    return True
        return False

    def _apply_aging(self) -> None:
        if not self._config.aging_enabled:
            return
        now = time.monotonic()
        for doc in self._documents.values():
            if doc.state != SchedulingDocumentState.READY:
                continue
            if doc.waiting_since is None:
                continue
            waited = now - doc.waiting_since
            new_aging = int(waited / self._config.aging_interval_seconds)
            if new_aging > doc.aging_adjustment:
                old = doc.aging_adjustment
                doc.aging_adjustment = new_aging
                doc.effective_priority = max(0, doc.base_priority_value - new_aging)
                if doc.effective_priority < _PRIORITY_CLASS_ORDER.get(
                    PriorityClass.INTERACTIVE_SHORT, 0
                ):
                    doc.effective_priority = 0
                self._record_event(
                    "priority_aged",
                    document_id=doc.document_id,
                    old_aging=old,
                    new_aging=new_aging,
                )

    def _remove_from_ready(self, document_id: str, priority_class: PriorityClass) -> None:
        queue = self._ready_by_class.get(priority_class)
        if queue is None:
            return
        with contextlib.suppress(ValueError):
            queue.remove(document_id)

    def _find_unit(
        self, work_unit_id: str
    ) -> tuple[ScheduledDocument | None, SchedulerWorkUnit | None]:
        for doc in self._documents.values():
            for unit in doc.work_units:
                if unit.work_unit_id == work_unit_id:
                    return doc, unit
        return None, None

    def _record_event(self, event_type: str, **kwargs: Any) -> None:
        entry: dict[str, Any] = {
            "event": event_type,
            "turn": self._turn_number,
            "timestamp": time.monotonic(),
        }
        entry.update(kwargs)
        self._history.append(entry)
