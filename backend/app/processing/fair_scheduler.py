"""Fair OCR page-chunk scheduling (Phase 4.5).

Enabled only when ``FAIR_OCR_SCHEDULING_ENABLED`` is true. Processes a bounded
chunk of expensive OCR pages, checkpoints, then yields to another ready
document. Fast non-OCR routes are not forced behind long OCR queues.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FairScheduleState:
    """Per-document OCR chunk progress."""

    document_id: str
    full_ocr_pages: list[int] = field(default_factory=list)
    next_index: int = 0
    chunk_size: int = 5

    @property
    def remaining(self) -> int:
        return max(0, len(self.full_ocr_pages) - self.next_index)

    def take_chunk(self) -> list[int]:
        if self.next_index >= len(self.full_ocr_pages):
            return []
        end = min(len(self.full_ocr_pages), self.next_index + self.chunk_size)
        chunk = self.full_ocr_pages[self.next_index : end]
        self.next_index = end
        return chunk

    @property
    def complete(self) -> bool:
        return self.next_index >= len(self.full_ocr_pages)


@dataclass(slots=True)
class FairOcrScheduler:
    """Round-robin chunk scheduler across documents with OCR work remaining."""

    chunk_size: int = 5
    enabled: bool = False
    _states: dict[str, FairScheduleState] = field(default_factory=dict)
    _order: list[str] = field(default_factory=list)
    _cursor: int = 0

    def register(self, document_id: str, full_ocr_pages: list[int]) -> FairScheduleState:
        state = FairScheduleState(
            document_id=document_id,
            full_ocr_pages=list(full_ocr_pages),
            chunk_size=self.chunk_size,
        )
        self._states[document_id] = state
        if document_id not in self._order:
            self._order.append(document_id)
        return state

    def unregister(self, document_id: str) -> None:
        self._states.pop(document_id, None)
        if document_id in self._order:
            self._order.remove(document_id)
        if self._cursor >= len(self._order):
            self._cursor = 0

    def next_chunk(self) -> tuple[str, list[int]] | None:
        """Return (document_id, page_numbers) for the next fair chunk."""

        if not self.enabled or not self._order:
            return None
        checked = 0
        while checked < len(self._order):
            if self._cursor >= len(self._order):
                self._cursor = 0
            doc_id = self._order[self._cursor]
            self._cursor = (self._cursor + 1) % max(1, len(self._order))
            state = self._states.get(doc_id)
            checked += 1
            if state is None or state.complete:
                continue
            chunk = state.take_chunk()
            if chunk:
                return doc_id, chunk
        return None

    def has_work(self) -> bool:
        return any(not s.complete for s in self._states.values())
