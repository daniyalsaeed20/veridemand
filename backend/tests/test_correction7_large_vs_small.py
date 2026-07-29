"""Correction 7 decisive fairness: a small document must not wait for a large one.

Real coordinator, real FairDocumentScheduler, real VisualOcrService. Only the
canonicalisation, native, and OCR-worker boundaries are faked so the test can
run without Paddle while still exercising page-quantum interleaving.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from backend.app.canonical.models import CanonicalisationResult
from backend.app.contracts.canonical import (
    CanonicalisationMethod,
    CanonicalPageMetadata,
    CanonicalPageSourceType,
    CanonicalStatus,
)
from backend.app.contracts.documents import DocumentStatus, PageCountStatus
from backend.app.contracts.jobs import JobStatus
from backend.app.contracts.native import (
    DocumentSourcePolicy,
    NativeDocumentSummary,
    NativePageDecision,
    NativePageMetrics,
    NativePageResult,
    NativePageTrustResult,
    NativeProcessingStatus,
    NativeProgress,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.visual import (
    PageResultState,
    VisualPageResult,
    VisualPageStatus,
    VisualProcessingStatus,
    source_label_for_page_result_state,
)
from backend.app.extraction.native.runner import NativeWorkerOutcome
from backend.app.extraction.visual.models import OcrRuntimeConfig, VisualWorkerRequest
from backend.app.extraction.visual.result_store import publish_page_atomic
from backend.app.extraction.visual.service import VisualOcrService
from backend.app.processing.cancellation import CancellationToken
from backend.app.processing.fair_scheduler import FairDocumentScheduler, SchedulerConfig
from backend.app.processing.models import ProcessingJob
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore

from .conftest import build_coordinator, build_runtime, register_document

_PAGE_SECONDS = 0.05


def _settings(tmp_path: Path, *, quantum: int = 1) -> Settings:
    return Settings(
        temp_root=tmp_path / "temp",
        ocr_enabled=True,
        render_concurrency=1,
        ocr_concurrency=1,
        # Routing and visibility probes need a real rendered page; this test
        # exercises scheduling, so select heavy pages from native trust alone.
        hybrid_page_routing_enabled=False,
        native_visibility_probe_enabled=False,
        fair_ocr_scheduling_enabled=True,
        fair_ocr_page_quantum=quantum,
    )


class PageCountProcessor:
    """Canonicalise to a fixed page count without touching a real PDF."""

    def __init__(self, file_store: FileStore, page_counts: dict[str, int]) -> None:
        self._file_store = file_store
        self._page_counts = page_counts

    async def canonicalise(
        self,
        session: RuntimeSession,
        document: RuntimeDocument,
        job: ProcessingJob,
        cancellation: CancellationToken,
    ) -> CanonicalisationResult:
        path = self._file_store.canonical_path(session.session_id, document.document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4 fake")
        count = self._page_counts[document.document_id]
        pages = [
            CanonicalPageMetadata(
                page_number=n,
                width_points=612.0,
                height_points=792.0,
                intrinsic_rotation=0,
                source_type=CanonicalPageSourceType.TEXT,
            )
            for n in range(1, count + 1)
        ]
        result = CanonicalisationResult(
            pages=pages,
            method=CanonicalisationMethod.REPORTLAB_TEXT_PDF,
            sha256="a" * 64,
            size_bytes=path.stat().st_size,
            path=path,
            libreoffice_version=None,
            warnings=[],
        )
        document.canonical_view_available = True
        document.canonical_size_bytes = result.size_bytes
        document.canonical_sha256 = result.sha256
        document.canonical_page_count = count
        document.canonicalisation_method = result.method
        document.canonical_pages = list(pages)
        document.canonical_status = CanonicalStatus.READY
        document.canonical_created_at = datetime.now(UTC)
        document.page_count = count
        document.page_count_status = PageCountStatus.KNOWN
        return result


def _metrics() -> NativePageMetrics:
    return NativePageMetrics(
        raw_character_count=0,
        deduplicated_character_count=0,
        word_count=0,
        character_count=0,
        duplicate_character_ratio=0.0,
        replacement_character_ratio=0.0,
        control_character_ratio=0.0,
        private_use_character_ratio=0.0,
        unassigned_character_ratio=0.0,
        noncharacter_ratio=0.0,
        unprintable_character_ratio=0.0,
        cid_token_ratio=0.0,
        invalid_geometry_ratio=0.0,
        out_of_bounds_character_ratio=0.0,
        zero_area_character_ratio=0.0,
        invalid_word_geometry_ratio=0.0,
        single_character_word_ratio=0.0,
        symbol_only_word_ratio=0.0,
        alphanumeric_word_ratio=0.0,
        very_long_token_ratio=0.0,
        repeated_token_ratio=0.0,
        whitespace_ratio=0.0,
        font_count=0,
        missing_font_ratio=0.0,
        upright_character_ratio=1.0,
        extraction_order_backtrack_ratio=0.0,
        characters_per_page_area=0.0,
        words_per_page_area=0.0,
        image_count=1,
        largest_image_area_ratio=1.0,
        total_clipped_image_area_ratio=0.0,
        page_dimension_match=True,
    )


class RoutedNativeService:
    """Native stage that marks each document as scanned or natively accepted."""

    def __init__(self, needs_visual: dict[str, bool]) -> None:
        self._needs_visual = needs_visual
        self._pages: dict[tuple[str, str, int], NativePageResult] = {}

    async def extract_document(self, **kwargs: Any) -> NativeWorkerOutcome:
        session_id = str(kwargs.get("session_id") or "")
        document_id = str(kwargs.get("document_id") or "")
        pages_meta = kwargs.get("canonical_pages") or []
        page_count = len(pages_meta) if isinstance(pages_meta, list) else 1
        scanned = self._needs_visual.get(document_id, True)
        decision = NativePageDecision.REJECTED if scanned else NativePageDecision.ACCEPTED
        source_mode = SourceMode.VISUAL_AUTHORITY if scanned else SourceMode.NATIVE_AUTHORITY

        page_results: list[NativePageResult] = []
        for n in range(1, page_count + 1):
            trust = NativePageTrustResult(
                page_number=n,
                decision=decision,
                source_mode=source_mode,
                native_text_present=not scanned,
                native_trust_score=0.0 if scanned else 0.95,
                trust_policy_version="phase3-v1",
                hard_rejection=scanned,
                reason_codes=["native_text_absent"] if scanned else [],
                warning_codes=[],
                metrics=_metrics(),
                visual_agreement_status=VisualAgreementStatus.NOT_EVALUATED_PHASE_3,
                visual_agreement_score=None,
                native_result_available=not scanned,
                visual_processing_required=scanned,
            )
            page = NativePageResult(
                page_number=n,
                decision=decision,
                source_mode=source_mode,
                trust=trust,
                words=[],
                characters=[],
                provisional_native_text=None if scanned else "ok",
            )
            page_results.append(page)
            self._pages[(session_id, document_id, n)] = page

        summary = NativeDocumentSummary(
            document_id=document_id,
            native_processing_status=NativeProcessingStatus.COMPLETE,
            document_source_policy=(
                DocumentSourcePolicy.VISUAL_AUTHORITY
                if scanned
                else DocumentSourcePolicy.NATIVE_AUTHORITY
            ),
            trust_policy_version="phase3-v1",
            page_count=page_count,
            pages_accepted=0 if scanned else page_count,
            pages_rejected=page_count if scanned else 0,
            pages_absent=0,
            pages_errored=0,
            pages_suppressed=0,
            native_result_available=not scanned,
            visual_processing_required=scanned,
            native_extraction_performed=True,
            final_result_available=False,
            progress=NativeProgress(percent=35, pages_completed=page_count, pages_total=page_count),
            page_decisions=[p.trust for p in page_results],
            warnings=[],
            created_at=datetime.now(UTC),
            user_status_message="Native trust evaluated.",
        )
        return NativeWorkerOutcome(summary=summary, pages=page_results, exit_code=0)

    def load_page(
        self, session_id: str, document_id: str, page_number: int
    ) -> NativePageResult | None:
        return self._pages.get((session_id, document_id, page_number))

    def load_summary(self, session_id: str, document_id: str) -> None:
        return None

    def republish_page(self, session_id: str, document_id: str, page: NativePageResult) -> None:
        return None

    def cleanup_staging(self, session_id: str, job_id: str) -> None:
        return None

    def delete_results(self, session_id: str, document_id: str) -> None:
        return None

    def describe_runtime(self) -> dict[str, str]:
        return {"native_service_class": type(self).__qualname__}


class DeterministicFakeOcrWorkerManager:
    """Stand-in for the Paddle worker: one timed, published page at a time."""

    def __init__(self, timeline: list[tuple[str, str, int]]) -> None:
        self.timeline = timeline
        self.ready = True
        self.generation = 1

    def config_from_settings(self) -> OcrRuntimeConfig:
        return OcrRuntimeConfig()

    async def process_document(
        self,
        request: VisualWorkerRequest,
        *,
        cancel_token: CancellationToken | None = None,
        on_progress: Callable[[dict[str, Any]], Any] | None = None,
        attempt_number: int = 1,
    ) -> list[dict[str, Any]]:
        output_dir = Path(request.page_output_dir)
        for ref in request.pages:
            page_number = ref.page_number
            self.timeline.append(("started", request.document_id, page_number))
            if on_progress is not None:
                await on_progress({"type": "page.started", "page_number": page_number})
            await asyncio.sleep(_PAGE_SECONDS)
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            publish_page_atomic(
                VisualPageResult(
                    page_number=page_number,
                    status=VisualPageStatus.COMPLETED,
                    source_mode=SourceMode.VISUAL_AUTHORITY,
                    page_result_state=PageResultState.FULL_VISUAL_OCR,
                    source_label=source_label_for_page_result_state(
                        PageResultState.FULL_VISUAL_OCR
                    ),
                    line_count=1,
                    word_count=1,
                    visual_result_available=True,
                    visual_processing_attempted=True,
                ),
                output_dir,
            )
            self.timeline.append(("completed", request.document_id, page_number))
            if on_progress is not None:
                await on_progress(
                    {
                        "type": "page.completed",
                        "page_number": page_number,
                        "status": "completed",
                    }
                )
        return []


async def _wait_for(predicate: Callable[[], bool], max_wait: float = 20.0) -> None:
    async def _run() -> None:
        while not predicate():  # noqa: ASYNC110 - polling coordinator state in tests
            await asyncio.sleep(0.01)

    await asyncio.wait_for(_run(), max_wait)


def _pages_for(timeline: list[tuple[str, str, int]], document_id: str) -> list[int]:
    return [page for event, doc, page in timeline if doc == document_id and event == "completed"]


def _first_index(
    timeline: list[tuple[str, str, int]], document_id: str, event: str = "started"
) -> int:
    for index, (kind, doc, _page) in enumerate(timeline):
        if doc == document_id and kind == event:
            return index
    raise AssertionError(f"no {event} event for {document_id}")


def _last_index(timeline: list[tuple[str, str, int]], document_id: str) -> int:
    indexes = [i for i, (_k, doc, _p) in enumerate(timeline) if doc == document_id]
    assert indexes, f"no timeline events for {document_id}"
    return indexes[-1]


@pytest.mark.asyncio
async def test_small_document_interleaves_with_running_large_document(tmp_path: Path) -> None:
    """A 2-page document queued mid-flight preempts a running 12-page document."""

    settings = _settings(tmp_path)
    timeline: list[tuple[str, str, int]] = []
    registry, queue, file_store = build_runtime(settings)
    worker = DeterministicFakeOcrWorkerManager(timeline)
    visual = VisualOcrService(settings, worker)  # type: ignore[arg-type]
    session = await registry.create()
    large = register_document(file_store, session)
    small = register_document(file_store, session)
    page_counts = {large.document_id: 12, small.document_id: 2}

    coordinator = build_coordinator(
        registry,
        queue,
        file_store,
        PageCountProcessor(file_store, page_counts),
        settings=settings,
        native_service=RoutedNativeService({large.document_id: True, small.document_id: True}),
        visual_service=visual,
    )
    coordinator.set_scheduler(FairDocumentScheduler(SchedulerConfig(enabled=True, page_quantum=1)))
    coordinator.start()
    coordinator.start_heavy_consumer()
    try:
        await coordinator.enqueue_documents(session, [large.document_id])
        # Only queue the small document once the large one owns the OCR worker.
        await _wait_for(lambda: len(_pages_for(timeline, large.document_id)) >= 1)
        await coordinator.enqueue_documents(session, [small.document_id])
        await _wait_for(
            lambda: (
                small.status is DocumentStatus.VISUAL_PROCESSING_COMPLETE
                and large.status is DocumentStatus.VISUAL_PROCESSING_COMPLETE
            )
        )
    finally:
        await coordinator.stop()

    large_pages = _pages_for(timeline, large.document_id)
    small_pages = _pages_for(timeline, small.document_id)
    assert sorted(large_pages) == list(range(1, 13))
    assert sorted(small_pages) == [1, 2]
    assert len(large_pages) == len(set(large_pages)), "large document page processed twice"
    assert len(small_pages) == len(set(small_pages)), "small document page processed twice"

    # Decisive: both of the small document's pages run before the large document
    # reaches page 12, so the small document never waits out the whole queue.
    small_last = _last_index(timeline, small.document_id)
    large_last = _last_index(timeline, large.document_id)
    assert small_last < large_last
    small_start = _first_index(timeline, small.document_id)
    assert _first_index(timeline, large.document_id) < small_start, (
        "the large document should already be running when the small one arrives"
    )
    large_pages_before_small = sum(
        1
        for event, doc, _page in timeline[:small_start]
        if doc == large.document_id and event == "completed"
    )
    assert large_pages_before_small <= 6, (
        f"small document waited for {large_pages_before_small} large pages"
    )

    for document in (large, small):
        summary = visual.load_summary(session.session_id, document.document_id)
        assert summary is not None
        assert summary.visual_processing_status is VisualProcessingStatus.VISUAL_PROCESSING_COMPLETE
        assert summary.pages_completed == page_counts[document.document_id]
        job = next(j for j in session.jobs.values() if j.document_id == document.document_id)
        assert job.status is JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_small_document_admitted_together_runs_first(tmp_path: Path) -> None:
    """Queued together, the short document is served before the large backlog."""

    settings = _settings(tmp_path)
    timeline: list[tuple[str, str, int]] = []
    registry, queue, file_store = build_runtime(settings)
    worker = DeterministicFakeOcrWorkerManager(timeline)
    visual = VisualOcrService(settings, worker)  # type: ignore[arg-type]
    session = await registry.create()
    large = register_document(file_store, session)
    small = register_document(file_store, session)

    coordinator = build_coordinator(
        registry,
        queue,
        file_store,
        PageCountProcessor(file_store, {large.document_id: 12, small.document_id: 2}),
        settings=settings,
        native_service=RoutedNativeService({large.document_id: True, small.document_id: True}),
        visual_service=visual,
    )
    coordinator.set_scheduler(FairDocumentScheduler(SchedulerConfig(enabled=True, page_quantum=1)))
    coordinator.start()
    coordinator.start_heavy_consumer()
    try:
        await coordinator.enqueue_documents(session, [large.document_id, small.document_id])
        await _wait_for(
            lambda: (
                small.status is DocumentStatus.VISUAL_PROCESSING_COMPLETE
                and large.status is DocumentStatus.VISUAL_PROCESSING_COMPLETE
            )
        )
    finally:
        await coordinator.stop()

    assert sorted(_pages_for(timeline, large.document_id)) == list(range(1, 13))
    assert sorted(_pages_for(timeline, small.document_id)) == [1, 2]
    assert _last_index(timeline, small.document_id) < _last_index(timeline, large.document_id)


@pytest.mark.asyncio
async def test_native_document_completes_while_large_document_runs(tmp_path: Path) -> None:
    """A native-only document bypasses the heavy queue entirely."""

    settings = _settings(tmp_path)
    timeline: list[tuple[str, str, int]] = []
    registry, queue, file_store = build_runtime(settings)
    worker = DeterministicFakeOcrWorkerManager(timeline)
    visual = VisualOcrService(settings, worker)  # type: ignore[arg-type]
    session = await registry.create()
    large = register_document(file_store, session)
    native = register_document(file_store, session)
    page_counts = {large.document_id: 12, native.document_id: 2}

    coordinator = build_coordinator(
        registry,
        queue,
        file_store,
        PageCountProcessor(file_store, page_counts),
        settings=settings,
        native_service=RoutedNativeService({large.document_id: True, native.document_id: False}),
        visual_service=visual,
    )
    coordinator.set_scheduler(FairDocumentScheduler(SchedulerConfig(enabled=True, page_quantum=1)))
    coordinator.start()
    coordinator.start_heavy_consumer()
    try:
        await coordinator.enqueue_documents(session, [large.document_id, native.document_id])
        await _wait_for(
            lambda: (
                native.status
                in (
                    DocumentStatus.VISUAL_PROCESSING_COMPLETE,
                    DocumentStatus.NATIVE_TRUST_COMPLETE,
                )
            )
        )
        pages_done_when_native_finished = len(_pages_for(timeline, large.document_id))
        assert pages_done_when_native_finished < 12, (
            "native document waited for the whole large document"
        )
        await _wait_for(lambda: large.status is DocumentStatus.VISUAL_PROCESSING_COMPLETE)
    finally:
        await coordinator.stop()

    assert not _pages_for(timeline, native.document_id)
    assert sorted(_pages_for(timeline, large.document_id)) == list(range(1, 13))
    native_summary = visual.load_summary(session.session_id, native.document_id)
    assert native_summary is not None
    assert native_summary.pages_selected == 0


@pytest.mark.asyncio
async def test_cancelling_a_released_document_stops_its_pages(tmp_path: Path) -> None:
    """Cancelling a document whose job was already released still finalises it."""

    settings = _settings(tmp_path)
    timeline: list[tuple[str, str, int]] = []
    registry, queue, file_store = build_runtime(settings)
    worker = DeterministicFakeOcrWorkerManager(timeline)
    visual = VisualOcrService(settings, worker)  # type: ignore[arg-type]
    session = await registry.create()
    large = register_document(file_store, session)

    coordinator = build_coordinator(
        registry,
        queue,
        file_store,
        PageCountProcessor(file_store, {large.document_id: 12}),
        settings=settings,
        native_service=RoutedNativeService({large.document_id: True}),
        visual_service=visual,
    )
    scheduler = FairDocumentScheduler(SchedulerConfig(enabled=True, page_quantum=1))
    coordinator.set_scheduler(scheduler)
    coordinator.start()
    coordinator.start_heavy_consumer()
    try:
        await coordinator.enqueue_documents(session, [large.document_id])
        await _wait_for(lambda: len(_pages_for(timeline, large.document_id)) >= 1)
        await coordinator.cancel_document(session, large.document_id)
        pages_at_cancel = len(_pages_for(timeline, large.document_id))
        await asyncio.sleep(_PAGE_SECONDS * 4)
        assert len(_pages_for(timeline, large.document_id)) <= pages_at_cancel + 1
    finally:
        await coordinator.stop()

    assert large.status is DocumentStatus.CANCELLED
    job = next(j for j in session.jobs.values() if j.document_id == large.document_id)
    assert job.status is JobStatus.CANCELLED
    sched_doc = scheduler.get_document(large.document_id)
    assert sched_doc is not None
    assert sched_doc.remaining_work == 0


@pytest.mark.asyncio
async def test_disabled_fair_mode_runs_whole_document(tmp_path: Path) -> None:
    """With fair scheduling off, each document still runs contiguously."""

    settings = _settings(tmp_path).model_copy(update={"fair_ocr_scheduling_enabled": False})
    timeline: list[tuple[str, str, int]] = []
    registry, queue, file_store = build_runtime(settings)
    worker = DeterministicFakeOcrWorkerManager(timeline)
    visual = VisualOcrService(settings, worker)  # type: ignore[arg-type]
    session = await registry.create()
    first = register_document(file_store, session)
    second = register_document(file_store, session)
    page_counts = {first.document_id: 3, second.document_id: 3}

    coordinator = build_coordinator(
        registry,
        queue,
        file_store,
        PageCountProcessor(file_store, page_counts),
        settings=settings,
        native_service=RoutedNativeService({first.document_id: True, second.document_id: True}),
        visual_service=visual,
    )
    coordinator.set_scheduler(FairDocumentScheduler(SchedulerConfig(enabled=False, page_quantum=1)))
    coordinator.start()
    coordinator.start_heavy_consumer()
    try:
        await coordinator.enqueue_documents(session, [first.document_id, second.document_id])
        await _wait_for(
            lambda: (
                first.status is DocumentStatus.VISUAL_PROCESSING_COMPLETE
                and second.status is DocumentStatus.VISUAL_PROCESSING_COMPLETE
            )
        )
    finally:
        await coordinator.stop()

    ordering = [doc for _event, doc, _page in timeline]
    first_block = [doc for doc in ordering if doc == first.document_id]
    assert ordering[: len(first_block)] == first_block, "documents interleaved while disabled"
    assert sorted(_pages_for(timeline, first.document_id)) == [1, 2, 3]
    assert sorted(_pages_for(timeline, second.document_id)) == [1, 2, 3]
