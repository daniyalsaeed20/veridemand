"""Processing coordinator: a single worker over the in-memory queue.

Owns the queue worker task, job state transitions, cancellation, session-state
updates, event publication, and graceful shutdown. Each job runs canonicalisation
then native extraction sequentially. FastAPI ``BackgroundTasks`` is deliberately
not used for the queue.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from backend.app.canonical.errors import CanonicalisationError
from backend.app.canonical.processor import CanonicalisationProcessor
from backend.app.contracts.canonical import CanonicalStatus
from backend.app.contracts.documents import DocumentStatus, PageCountStatus
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.identifiers import new_job_id
from backend.app.contracts.jobs import JobStatus, JobSummary
from backend.app.contracts.native import NativeDocumentSummary, NativePageDecision
from backend.app.contracts.processing import IgnoredDocument
from backend.app.contracts.progress import ProgressEventType
from backend.app.contracts.routing import PageRoute
from backend.app.extraction.native.errors import NativeExtractionError
from backend.app.extraction.native.service import NativeExtractionService
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.service import VisualOcrService
from backend.app.observability.errors import ApiException
from backend.app.observability.stage_log import log_progress, log_stage
from backend.app.processing.cancellation import JobCancelledError
from backend.app.processing.eta import EtaCostRoute, EtaEstimator, page_route_to_cost_route
from backend.app.processing.models import ProcessingJob
from backend.app.processing.progress_model import (
    OVERALL_CAP,
    OVERALL_NATIVE_POLICY_END,
    OVERALL_VISUAL_SELECT_END,
    PAGE_GROUPED,
    PAGE_MAPPING_DONE,
    PAGE_OCR_PIPELINE_DONE,
    PAGE_PREPROCESSED,
    PAGE_PUBLISHED,
    PAGE_QUEUED,
    PAGE_RENDERED,
    MajorPhase,
    OperationStatus,
    ProgressKind,
    ProgressSnapshot,
)
from backend.app.processing.queue import JobQueue, QueueClosedError
from backend.app.progress.broker import EventBroker
from backend.app.progress.models import BrokerClosedError
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.sessions.registry import SessionRegistry
from backend.app.sessions.service import recompute_session_status
from backend.app.storage.file_store import FileStore

logger = logging.getLogger("veridemand.processing")

_FAILURE_CODE = "canonicalisation_failed"
_DOCUMENT_STAGE = "canonicalising"
_NATIVE_STAGE = "extracting_native"
_VISUAL_STAGE = "visual_ocr"
_MAX_CANONICAL_PROGRESS = 15
_NATIVE_INSPECT_PROGRESS = 16
_NATIVE_PAGE_START = 17
_NATIVE_PAGE_END = 32
_NATIVE_POLICY_PROGRESS = 34
_MAX_NATIVE_PROGRESS_PERCENT = 35
_VISUAL_SELECT_PROGRESS = 37
_VISUAL_PAGE_START = 41
_VISUAL_PAGE_END = 63
_VISUAL_GROUP_PROGRESS = 64
_MAX_PROGRESS_PERCENT = 65
_PROGRESS_STARTED = 2
_PHASE4_COMPLETE_MESSAGE = (
    "Printed visual OCR complete. Handwriting and final document structure have not been evaluated."
)


async def _safe_publish(broker: EventBroker, event: ProgressEventType, **fields: object) -> None:
    """Publish a progress event; never abort core processing on telemetry failure."""

    try:
        await broker.publish(event, **fields)  # type: ignore[arg-type]
    except BrokerClosedError:
        return
    except Exception as publish_exc:
        logger.exception(
            "progress_publication_failed",
            extra={
                "exception_type": type(publish_exc).__name__,
                "safe_error_code": ErrorCode.INTERNAL_ERROR.value,
                "failing_component": "EventBroker",
                "failing_operation": "visual_progress_creation",
                "document_id": fields.get("document_id"),
                "job_id": fields.get("job_id"),
                "page_number": fields.get("page_number"),
                "document_page_number": fields.get("document_page_number"),
                "event_sequence": fields.get("event_sequence"),
                "progress_version": fields.get("progress_version"),
                "event_id": fields.get("event_id"),
                "operation_id": fields.get("operation_id"),
                "operation": fields.get("operation"),
                "operation_status": fields.get("operation_status"),
                "attempt_number": fields.get("attempt_number"),
                "progress_event": getattr(event, "value", str(event)),
            },
        )


class ProcessingCoordinator:
    """Coordinates canonicalisation, native trust, and visual OCR with one worker."""

    def __init__(
        self,
        registry: SessionRegistry,
        job_queue: JobQueue,
        processor: CanonicalisationProcessor,
        file_store: FileStore,
        native_service: NativeExtractionService,
        visual_service: VisualOcrService | None = None,
        *,
        worker_count: int = 1,
        max_pages_per_session: int = 500,
    ) -> None:
        if worker_count != 1:
            raise ValueError("Phase 4 requires exactly one processing worker.")
        self._registry = registry
        self._queue = job_queue
        self._processor = processor
        self._file_store = file_store
        self._native = native_service
        self._visual = visual_service
        self._max_pages_per_session = max_pages_per_session
        self._worker: asyncio.Task[None] | None = None
        self._current_job: ProcessingJob | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running and self._worker is not None and not self._worker.done()

    def describe_native_runtime(self) -> dict[str, str]:
        """Return concrete native wiring classes for production-path assertions."""

        described = self._native.describe_runtime()
        described["canonical_processor_class"] = type(self._processor).__qualname__
        described["coordinator_class"] = type(self).__qualname__
        if self._visual is not None:
            described["visual_service_class"] = type(self._visual).__qualname__
        return described

    def start(self) -> None:
        if self._worker is not None:
            return
        self._running = True
        self._worker = asyncio.create_task(self._worker_loop(), name="canonicalisation-worker")

    async def stop(self) -> None:
        """Stop accepting jobs, cancel active work, and await worker termination."""

        self._running = False
        await self._queue.close()
        if self._current_job is not None:
            self._current_job.request_cancellation()
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    async def enqueue_documents(
        self, session: RuntimeSession, document_ids: list[str] | None
    ) -> tuple[list[JobSummary], list[IgnoredDocument]]:
        """Queue eligible ``uploaded`` documents; ignore everything else."""

        queued: list[JobSummary] = []
        ignored: list[IgnoredDocument] = []
        async with session.state_lock:
            if document_ids is None:
                targets = list(session.documents.values())
            else:
                for document_id in document_ids:
                    if document_id not in session.documents:
                        raise ApiException(
                            status_code=404,
                            code=ErrorCode.DOCUMENT_NOT_FOUND,
                            message="Document not found in this session.",
                            document_id=document_id,
                        )
                targets = [session.documents[document_id] for document_id in document_ids]

            for document in targets:
                if document.status is not DocumentStatus.UPLOADED:
                    ignored.append(
                        IgnoredDocument(
                            document_id=document.document_id,
                            reason=f"Document is '{document.status.value}', not 'uploaded'.",
                        )
                    )
                    continue
                job = ProcessingJob(
                    job_id=new_job_id(),
                    session_id=session.session_id,
                    document_id=document.document_id,
                )
                session.jobs[job.job_id] = job
                document.status = DocumentStatus.QUEUED
                document.canonical_status = CanonicalStatus.QUEUED
                document.active_job_id = job.job_id
                try:
                    await self._queue.enqueue(job)
                except QueueClosedError:
                    raise ApiException(
                        status_code=503,
                        code=ErrorCode.QUEUE_CLOSED,
                        message="The processing queue is not accepting work.",
                    ) from None
                position = await self._queue.position(job.job_id)
                await _safe_publish(
                    session.broker,
                    ProgressEventType.DOCUMENT_QUEUED,
                    document_id=document.document_id,
                    job_id=job.job_id,
                    queue_position=position,
                    document_status=DocumentStatus.QUEUED,
                )
                await _safe_publish(
                    session.broker,
                    ProgressEventType.JOB_QUEUED,
                    document_id=document.document_id,
                    job_id=job.job_id,
                    queue_position=position,
                    job_status=JobStatus.QUEUED,
                )
                queued.append(job.to_summary())

            recompute_session_status(session)
        return queued, ignored

    async def cancel_document(self, session: RuntimeSession, document_id: str) -> RuntimeDocument:
        """Cancel a queued/canonicalising document."""

        async with session.state_lock:
            document = session.documents.get(document_id)
            if document is None:
                raise ApiException(
                    status_code=404,
                    code=ErrorCode.DOCUMENT_NOT_FOUND,
                    message="Document not found in this session.",
                    document_id=document_id,
                )

            if document.status is DocumentStatus.CANCELLED:
                return document

            if document.status in (
                DocumentStatus.UPLOADED,
                DocumentStatus.NATIVE_TRUST_COMPLETE,
                DocumentStatus.VISUAL_PROCESSING_COMPLETE,
                DocumentStatus.VISUAL_PROCESSING_PARTIAL,
                DocumentStatus.VISUAL_PROCESSING_FAILED,
                DocumentStatus.FAILED,
            ):
                raise ApiException(
                    status_code=409,
                    code=ErrorCode.INVALID_DOCUMENT_STATE,
                    message="No active job to cancel; remove the document instead.",
                    document_id=document_id,
                )

            job = session.jobs.get(document.active_job_id or "")
            if document.status is DocumentStatus.QUEUED:
                if job is not None:
                    await self._queue.cancel(job.job_id)
                    job.request_cancellation()
                    job.status = JobStatus.CANCELLED
                    job.finished_at = datetime.now(UTC)
                document.status = DocumentStatus.CANCELLED
                document.canonical_status = CanonicalStatus.CANCELLED
                await _safe_publish(
                    session.broker,
                    ProgressEventType.DOCUMENT_CANONICALISATION_CANCELLED,
                    document_id=document_id,
                    job_id=job.job_id if job else None,
                    document_status=DocumentStatus.CANCELLED,
                    canonical_status=CanonicalStatus.CANCELLED.value,
                )
                await _safe_publish(
                    session.broker,
                    ProgressEventType.DOCUMENT_CANCELLED,
                    document_id=document_id,
                    job_id=job.job_id if job else None,
                    document_status=DocumentStatus.CANCELLED,
                )
                if job is not None:
                    await _safe_publish(
                        session.broker,
                        ProgressEventType.JOB_CANCELLED,
                        document_id=document_id,
                        job_id=job.job_id,
                        job_status=JobStatus.CANCELLED,
                    )
            elif (
                document.status
                in (
                    DocumentStatus.CANONICALISING,
                    DocumentStatus.READY_FOR_EXTRACTION,
                    DocumentStatus.INSPECTING_NATIVE,
                    DocumentStatus.EXTRACTING_NATIVE,
                    DocumentStatus.VISUAL_PENDING,
                    DocumentStatus.VISUAL_PROCESSING,
                )
                and job is not None
            ):
                job.request_cancellation()

            recompute_session_status(session)
            return document

    async def remove_document(self, session: RuntimeSession, document_id: str) -> None:
        """Remove a non-active document and its files."""

        async with session.state_lock:
            document = session.documents.get(document_id)
            if document is None:
                raise ApiException(
                    status_code=404,
                    code=ErrorCode.DOCUMENT_NOT_FOUND,
                    message="Document not found in this session.",
                    document_id=document_id,
                )
            if document.status in (
                DocumentStatus.QUEUED,
                DocumentStatus.CANONICALISING,
                DocumentStatus.INSPECTING_NATIVE,
                DocumentStatus.EXTRACTING_NATIVE,
                DocumentStatus.VISUAL_PENDING,
                DocumentStatus.VISUAL_PROCESSING,
            ):
                raise ApiException(
                    status_code=409,
                    code=ErrorCode.DOCUMENT_PROCESSING,
                    message="Cancel the document before removing it.",
                    document_id=document_id,
                )

            self._file_store.remove_document_files(
                session.session_id, document_id, document.extension
            )
            session.accepted_bytes = max(0, session.accepted_bytes - document.size_bytes)
            if document.page_count is not None:
                session.known_pages = max(0, session.known_pages - document.page_count)
            terminal_jobs = [
                job_id
                for job_id, job in session.jobs.items()
                if job.document_id == document_id and job.is_terminal
            ]
            for job_id in terminal_jobs:
                del session.jobs[job_id]
            del session.documents[document_id]

            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_REMOVED,
                document_id=document_id,
            )
            recompute_session_status(session)

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            self._current_job = job
            try:
                await self._run_job(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error running canonicalisation job.")
            finally:
                self._current_job = None
                await self._queue.task_done(job.job_id)

    async def _run_job(self, job: ProcessingJob) -> None:
        session = self._registry.peek(job.session_id)
        if session is None or session.deleting:
            self._finalize_orphan(job)
            return
        document = session.documents.get(job.document_id)
        if document is None:
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(UTC)
            return
        if job.cancellation.cancelled:
            await self._finalize_cancelled(session, job, document)
            recompute_session_status(session)
            return

        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        job.queue_position = None
        document.status = DocumentStatus.CANONICALISING
        document.canonical_status = CanonicalStatus.CANONICALISING
        document.progress_percent = _PROGRESS_STARTED
        session.begin_admission()
        recompute_session_status(session)
        await _safe_publish(
            session.broker,
            ProgressEventType.JOB_STARTED,
            document_id=document.document_id,
            job_id=job.job_id,
            job_status=JobStatus.RUNNING,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_STARTED,
            document_id=document.document_id,
            job_id=job.job_id,
            stage=_DOCUMENT_STAGE,
            percent=_PROGRESS_STARTED,
            document_status=DocumentStatus.CANONICALISING,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_CANONICALISATION_STARTED,
            document_id=document.document_id,
            job_id=job.job_id,
            stage=_DOCUMENT_STAGE,
            percent=_PROGRESS_STARTED,
            document_status=DocumentStatus.CANONICALISING,
            canonical_status=CanonicalStatus.CANONICALISING.value,
        )

        previous_pages = document.page_count if document.page_count is not None else 0
        try:
            result = await self._processor.canonicalise(session, document, job, job.cancellation)
            new_pages = len(result.pages)
            projected = session.known_pages - previous_pages + new_pages
            if projected > self._max_pages_per_session:
                self._file_store.remove_file(
                    self._file_store.canonical_path(session.session_id, document.document_id)
                )
                self._file_store.remove_file(
                    self._file_store.canonical_part_path(session.session_id, document.document_id)
                )
                document.canonical_view_available = False
                document.canonical_status = CanonicalStatus.FAILED
                document.canonical_failure_code = (
                    ErrorCode.CANONICALISATION_PAGE_LIMIT_EXCEEDED.value
                )
                raise CanonicalisationError(
                    ErrorCode.CANONICALISATION_PAGE_LIMIT_EXCEEDED,
                    "Canonical page count would exceed the session page limit.",
                )
            session.known_pages = projected
            document.page_count = new_pages
            document.page_count_status = PageCountStatus.KNOWN
        except JobCancelledError:
            await self._finalize_cancelled(session, job, document)
        except CanonicalisationError as exc:
            logger.warning("Canonicalisation failed: %s", exc.code.value)
            await self._finalize_failed(session, job, document, code=exc.code.value)
        except Exception as exc:
            logger.warning("Canonicalisation failed for a document: %s", type(exc).__name__)
            await self._finalize_failed(session, job, document)
        else:
            method = (
                document.canonicalisation_method.value
                if document.canonicalisation_method is not None
                else None
            )
            document.status = DocumentStatus.READY_FOR_EXTRACTION
            document.progress_percent = _MAX_CANONICAL_PROGRESS
            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_CANONICALISATION_PROGRESS,
                document_id=document.document_id,
                job_id=job.job_id,
                percent=_MAX_CANONICAL_PROGRESS,
                document_status=DocumentStatus.READY_FOR_EXTRACTION,
                canonicalisation_method=method,
                canonical_page_count=document.canonical_page_count,
                canonical_status=CanonicalStatus.READY.value,
            )
            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_CANONICALISATION_COMPLETED,
                document_id=document.document_id,
                job_id=job.job_id,
                percent=_MAX_CANONICAL_PROGRESS,
                canonicalisation_method=method,
                canonical_page_count=document.canonical_page_count,
                canonical_status=CanonicalStatus.READY.value,
            )
            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_CANONICAL_READY,
                document_id=document.document_id,
                job_id=job.job_id,
                percent=_MAX_CANONICAL_PROGRESS,
                message="Canonical document ready.",
                canonicalisation_method=method,
                canonical_page_count=document.canonical_page_count,
                canonical_status=CanonicalStatus.READY.value,
            )
            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_READY_FOR_EXTRACTION,
                document_id=document.document_id,
                job_id=job.job_id,
                percent=_MAX_CANONICAL_PROGRESS,
                message="Canonical document ready. Native inspection starting.",
                document_status=DocumentStatus.READY_FOR_EXTRACTION,
            )
            try:
                native_summary = await self._run_native(session, job, document)
            except JobCancelledError:
                await self._finalize_cancelled(session, job, document)
            except NativeExtractionError as exc:
                logger.exception(
                    "Native extraction failed",
                    extra={
                        "document_id": document.document_id,
                        "job_id": job.job_id,
                        "error_code": exc.code.value,
                        "exception_type": exc.exception_type or type(exc).__name__,
                        "failing_component": exc.failing_component
                        or type(self._native).__qualname__,
                        "operation": exc.operation or "extract_document",
                        "worker_exit_code": exc.worker_exit_code,
                        "page_number": exc.page_number,
                        "processor_class": type(self._processor).__qualname__,
                        "native_service_class": type(self._native).__qualname__,
                    },
                )
                await self._finalize_native_failed(
                    session,
                    job,
                    document,
                    code=exc.code.value,
                    page_number=exc.page_number,
                    operation=exc.operation,
                )
            except Exception as exc:
                logger.exception(
                    "Native extraction failed",
                    extra={
                        "document_id": document.document_id,
                        "job_id": job.job_id,
                        "error_code": ErrorCode.NATIVE_EXTRACTION_FAILED.value,
                        "exception_type": type(exc).__name__,
                        "failing_component": type(self._native).__qualname__,
                        "operation": "extract_document",
                        "worker_exit_code": None,
                        "processor_class": type(self._processor).__qualname__,
                        "native_service_class": type(self._native).__qualname__,
                    },
                )
                await self._finalize_native_failed(
                    session,
                    job,
                    document,
                    code=ErrorCode.NATIVE_EXTRACTION_FAILED.value,
                )
            else:
                try:
                    await self._run_visual(session, job, document, native_summary)
                except JobCancelledError:
                    await self._finalize_cancelled(session, job, document)
                except Exception as visual_exc:
                    failing_operation = "visual_request_creation"
                    if isinstance(visual_exc, TypeError) and "unexpected keyword" in str(
                        visual_exc
                    ):
                        failing_operation = "visual_progress_creation"
                    logger.exception(
                        "Visual OCR failed exception_type=%s safe_error_code=%s "
                        "failing_component=%s failing_operation=%s",
                        type(visual_exc).__name__,
                        ErrorCode.OCR_RUNTIME_UNAVAILABLE.value,
                        "ProcessingCoordinator",
                        failing_operation,
                        extra={
                            "document_id": document.document_id,
                            "job_id": job.job_id,
                            "page_number": document.active_page_number,
                            "exception_type": type(visual_exc).__name__,
                            "safe_error_code": ErrorCode.OCR_RUNTIME_UNAVAILABLE.value,
                            "failing_component": "ProcessingCoordinator",
                            "failing_operation": failing_operation,
                            "visual_page_count": document.canonical_page_count,
                            "selected_page_count": document.pages_total,
                            "worker_generation": document.worker_generation,
                            "attempt_number": document.attempt_number,
                        },
                    )
                    # Preserve usable native/canonical results; prefer partial when
                    # native pages already exist.
                    had_native = bool(document.native_result_available)
                    document.status = (
                        DocumentStatus.VISUAL_PROCESSING_PARTIAL
                        if had_native
                        else DocumentStatus.VISUAL_PROCESSING_FAILED
                    )
                    document.progress_percent = _MAX_PROGRESS_PERCENT
                    document.failure_stage = failing_operation
                    document.failure_code = ErrorCode.OCR_RUNTIME_UNAVAILABLE.value
                    document.failure_message = "The OCR service failed to process this document."
                    document.visual_processing_performed = True
                    document.visual_result_available = False
                    if self._visual is not None:
                        try:
                            from backend.app.contracts.visual import VisualProcessingStatus

                            self._visual.publish_terminal_failure_summary(
                                session_id=session.session_id,
                                document_id=document.document_id,
                                page_count=document.canonical_page_count or 0,
                                error_code=ErrorCode.OCR_RUNTIME_UNAVAILABLE.value,
                                canonical_document_available=document.canonical_view_available,
                                native_pages_retained=(
                                    document.canonical_page_count or 0 if had_native else 0
                                ),
                                status=(
                                    VisualProcessingStatus.VISUAL_PROCESSING_PARTIAL
                                    if had_native
                                    else VisualProcessingStatus.VISUAL_PROCESSING_FAILED
                                ),
                                user_status_message=document.failure_message,
                            )
                        except Exception:
                            logger.exception(
                                "Visual terminal summary publication failed",
                                extra={
                                    "document_id": document.document_id,
                                    "job_id": job.job_id,
                                    "exception_type": "SummaryPublishError",
                                    "safe_error_code": ErrorCode.VISUAL_RESULT_PUBLISH_FAILED.value,
                                    "failing_component": "VisualOcrService",
                                    "failing_operation": "visual_summary_publication",
                                },
                            )
                    await _safe_publish(
                        session.broker,
                        ProgressEventType.DOCUMENT_VISUAL_PROCESSING_FAILED
                        if not had_native
                        else ProgressEventType.DOCUMENT_VISUAL_PROCESSING_PARTIAL,
                        document_id=document.document_id,
                        job_id=job.job_id,
                        percent=_MAX_PROGRESS_PERCENT,
                        document_status=document.status,
                        message=document.failure_message,
                    )
                else:
                    job.status = JobStatus.COMPLETED
                    job.finished_at = datetime.now(UTC)
                    await _safe_publish(
                        session.broker,
                        ProgressEventType.JOB_COMPLETED,
                        document_id=document.document_id,
                        job_id=job.job_id,
                        job_status=JobStatus.COMPLETED,
                    )
        finally:
            session.end_admission()
            recompute_session_status(session)

    async def _run_native(
        self,
        session: RuntimeSession,
        job: ProcessingJob,
        document: RuntimeDocument,
    ) -> NativeDocumentSummary:
        if document.canonicalisation_method is None or not document.canonical_pages:
            raise NativeExtractionError(
                ErrorCode.NATIVE_EXTRACTION_FAILED,
                "Canonical metadata is incomplete for native extraction.",
            )
        if job.cancellation.cancelled:
            raise JobCancelledError()

        document.status = DocumentStatus.INSPECTING_NATIVE
        document.progress_percent = _NATIVE_INSPECT_PROGRESS
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_NATIVE_INSPECTION_STARTED,
            document_id=document.document_id,
            job_id=job.job_id,
            stage=_NATIVE_STAGE,
            percent=_NATIVE_INSPECT_PROGRESS,
            document_status=DocumentStatus.INSPECTING_NATIVE,
            pages_total=len(document.canonical_pages),
        )

        document.status = DocumentStatus.EXTRACTING_NATIVE
        document.progress_percent = _NATIVE_PAGE_START
        pages_total = max(len(document.canonical_pages), 1)
        pages_completed = 0

        async def on_progress(payload: dict[str, object]) -> None:
            nonlocal pages_completed
            event_type = str(payload.get("type", ""))
            if event_type != "page_completed":
                return
            pages_completed += 1
            raw_page = payload.get("page_number", pages_completed)
            page_number = (
                int(raw_page) if isinstance(raw_page, (int, float, str)) else pages_completed
            )
            decision = str(payload.get("decision", ""))
            fraction = pages_completed / pages_total
            percent = int(_NATIVE_PAGE_START + (_NATIVE_PAGE_END - _NATIVE_PAGE_START) * fraction)
            percent = min(percent, _NATIVE_PAGE_END)
            document.progress_percent = percent
            event = ProgressEventType.DOCUMENT_NATIVE_PAGE_ACCEPTED
            if decision == NativePageDecision.REJECTED.value:
                event = ProgressEventType.DOCUMENT_NATIVE_PAGE_REJECTED
            elif decision == NativePageDecision.ABSENT.value:
                event = ProgressEventType.DOCUMENT_NATIVE_PAGE_ABSENT
            elif decision == NativePageDecision.ERROR.value:
                event = ProgressEventType.DOCUMENT_NATIVE_PAGE_ERROR
            log_stage(
                component="native",
                operation="page_completed",
                document_id=document.document_id,
                job_id=job.job_id,
                page_number=page_number,
                decision=decision,
                percent=percent,
            )
            score_raw = payload.get("native_trust_score")
            score = float(score_raw) if isinstance(score_raw, (int, float)) else None
            reasons_raw = payload.get("reason_codes")
            reasons = [str(item) for item in reasons_raw] if isinstance(reasons_raw, list) else []
            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_NATIVE_PAGE_STARTED,
                document_id=document.document_id,
                job_id=job.job_id,
                page_number=page_number,
                pages_completed=pages_completed,
                pages_total=pages_total,
                percent=percent,
            )
            await _safe_publish(
                session.broker,
                event,
                document_id=document.document_id,
                job_id=job.job_id,
                page_number=page_number,
                decision=decision,
                source_mode=str(payload.get("source_mode")) if payload.get("source_mode") else None,
                native_trust_score=score,
                reason_codes=reasons,
                pages_completed=pages_completed,
                pages_total=pages_total,
                percent=percent,
            )

        canonical_pdf = self._file_store.canonical_path(session.session_id, document.document_id)
        outcome = await self._native.extract_document(
            session_id=session.session_id,
            document_id=document.document_id,
            job_id=job.job_id,
            canonical_pdf=canonical_pdf,
            canonical_pages=document.canonical_pages,
            canonicalisation_method=document.canonicalisation_method,
            cancel_token=job.cancellation,
            on_progress=on_progress,
        )

        document.progress_percent = _NATIVE_POLICY_PROGRESS
        if outcome.summary.document_source_policy is not None:
            policy = outcome.summary.document_source_policy
            if policy.value == "visual_authority" and outcome.summary.pages_suppressed > 0:
                await _safe_publish(
                    session.broker,
                    ProgressEventType.DOCUMENT_NATIVE_DOCUMENT_ESCALATED,
                    document_id=document.document_id,
                    job_id=job.job_id,
                    percent=_NATIVE_POLICY_PROGRESS,
                    reason_codes=["document_visual_authority_escalation"],
                )

        document.status = DocumentStatus.NATIVE_TRUST_COMPLETE
        document.progress_percent = _MAX_NATIVE_PROGRESS_PERCENT
        document.native_extraction_performed = True
        document.native_result_available = outcome.summary.native_result_available
        document.visual_processing_required = outcome.summary.visual_processing_required
        document.document_source_policy = outcome.summary.document_source_policy
        document.user_status_message = outcome.summary.user_status_message

        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_NATIVE_EXTRACTION_COMPLETED,
            document_id=document.document_id,
            job_id=job.job_id,
            percent=_MAX_NATIVE_PROGRESS_PERCENT,
            document_status=DocumentStatus.NATIVE_TRUST_COMPLETE,
            pages_completed=pages_total,
            pages_total=pages_total,
            message=document.user_status_message,
        )
        return outcome.summary

    async def _run_visual(
        self,
        session: RuntimeSession,
        job: ProcessingJob,
        document: RuntimeDocument,
        native_summary: object,
    ) -> None:
        if self._visual is None:
            document.status = DocumentStatus.VISUAL_PROCESSING_COMPLETE
            document.progress_percent = _MAX_PROGRESS_PERCENT
            document.user_status_message = _PHASE4_COMPLETE_MESSAGE
            return

        if job.cancellation.cancelled:
            raise JobCancelledError()

        document.status = DocumentStatus.VISUAL_PENDING
        document.progress_percent = _VISUAL_SELECT_PROGRESS
        document.user_status_message = "Waiting for OCR worker"
        log_stage(
            component="visual",
            operation="visual_pending",
            document_id=document.document_id,
            job_id=job.job_id,
            percent=_VISUAL_SELECT_PROGRESS,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_VISUAL_PROCESSING_STARTED,
            document_id=document.document_id,
            job_id=job.job_id,
            stage=_VISUAL_STAGE,
            percent=_VISUAL_SELECT_PROGRESS,
            document_status=DocumentStatus.VISUAL_PENDING,
            message=document.user_status_message,
        )

        native_pages = {}
        page_count = len(document.canonical_pages)
        for page_number in range(1, page_count + 1):
            page = self._native.load_page(session.session_id, document.document_id, page_number)
            if page is not None:
                native_pages[page_number] = page

        document.status = DocumentStatus.VISUAL_PROCESSING
        pages_completed = 0
        pages_selected = page_count
        selection_started = False
        selection_completed = False
        native_pages_retained = 0
        embedded_ocr_pages_verified = 0
        targeted_repair_pages_selected = 0
        targeted_repair_pages_completed = 0
        full_ocr_pages_selected = 0
        full_ocr_pages_completed = 0
        visual_no_text_pages = 0
        failed_page_count = 0
        selected_page_numbers: list[int] = []
        progress_version = 1
        visual_settings = getattr(self._visual, "_settings", None)
        eta = EtaEstimator(
            minimum_sample_count=int(getattr(visual_settings, "eta_minimum_sample_count", 3)),
            stale_after_seconds=float(getattr(visual_settings, "eta_stale_after_seconds", 120.0)),
        )
        fair_enabled = bool(getattr(visual_settings, "fair_ocr_scheduling_enabled", False))
        document.fair_scheduling_enabled = fair_enabled
        document.document_pages_total = page_count
        document.document_started_at = document.document_started_at or datetime.now(UTC)
        document.document_started_at_timestamp = document.document_started_at
        document.phase_started_at = datetime.now(UTC)

        # Test-only inject: abort after native, before OCR request creation.
        inject_failure = bool(
            getattr(getattr(self._visual, "_settings", None), "ocr_inject_visual_failure", False)
        )
        if inject_failure:
            raise VisualOcrError(
                ErrorCode.OCR_RUNTIME_UNAVAILABLE,
                "Injected visual failure for acceptance testing.",
                operation="visual_request_creation",
                failing_component="ProcessingCoordinator",
                exception_type="InjectedVisualFailure",
            )

        snapshot = ProgressSnapshot(
            overall_percent=float(max(document.progress_percent, int(OVERALL_NATIVE_POLICY_END))),
            major_phase=MajorPhase.VISUAL_OCR,
            major_phase_percent=0.0,
            pages_selected=page_count,
            pages_total=page_count,
            document_pages_total=page_count,
            document_id=document.document_id,
            operation="visual_page_selection",
            operation_status=OperationStatus.QUEUED,
        )
        document.major_phase = MajorPhase.VISUAL_OCR.value
        document.current_operation = "visual_page_selection"
        document.operation_status = OperationStatus.QUEUED.value
        document.max_attempts = 2
        document.attempt_number = 1

        def _selected_index_for(doc_page: int | None) -> int | None:
            if doc_page is None or not selected_page_numbers:
                return None
            try:
                return selected_page_numbers.index(doc_page) + 1
            except ValueError:
                return None

        def _page_label(doc_page: int | None) -> str:
            sel = _selected_index_for(doc_page)
            parts: list[str] = []
            if doc_page is not None:
                parts.append(f"Document page {doc_page} of {page_count}")
            if sel is not None and pages_selected > 0:
                parts.append(f"Selected OCR page {sel} of {pages_selected}")
            return " · ".join(parts) if parts else "page"

        def _apply_snapshot(*, advance_version: bool = True) -> None:
            nonlocal progress_version
            if advance_version:
                progress_version += 1
            remaining_by_route = {
                EtaCostRoute.FULL_OCR_PRIMARY: max(
                    0, full_ocr_pages_selected - full_ocr_pages_completed
                ),
                EtaCostRoute.TARGETED_REPAIR: max(
                    0, targeted_repair_pages_selected - targeted_repair_pages_completed
                ),
                EtaCostRoute.EMBEDDED_OCR_VISUAL_CHECK: max(
                    0,
                    (embedded_ocr_pages_verified + targeted_repair_pages_selected)
                    - embedded_ocr_pages_verified
                    - targeted_repair_pages_completed,
                ),
                EtaCostRoute.DIGITAL_NATIVE: max(0, native_pages_retained),
            }
            # After routing, do not invent full-OCR remaining when none selected.
            if full_ocr_pages_selected == 0:
                remaining_by_route[EtaCostRoute.FULL_OCR_PRIMARY] = 0
            eta_snap = eta.estimate(
                remaining_by_route=remaining_by_route,
                queue_remaining_by_route=remaining_by_route,
                current_operation_route=page_route_to_cost_route(
                    document.current_route or PageRoute.FULL_VISUAL_OCR
                )
                if document.current_route
                else (
                    EtaCostRoute.DIGITAL_NATIVE
                    if full_ocr_pages_selected == 0 and pages_selected == 0
                    else EtaCostRoute.FULL_OCR_PRIMARY
                ),
                current_page_route=page_route_to_cost_route(
                    document.current_route or PageRoute.FULL_VISUAL_OCR
                )
                if document.current_route
                else None,
            )
            document.progress_percent = int(min(OVERALL_CAP, snapshot.overall_percent))
            document.major_phase = snapshot.major_phase.value
            document.major_phase_percent = snapshot.major_phase_percent
            document.page_percent = snapshot.page_percent
            document.document_page_number = snapshot.document_page_number
            document.active_page_number = snapshot.document_page_number
            document.document_pages_total = snapshot.document_pages_total or page_count
            document.selected_page_index = snapshot.selected_page_index
            document.selected_pages_total = snapshot.selected_pages_total or pages_selected
            document.visual_page_index = snapshot.visual_page_index
            document.visual_pages_total = snapshot.visual_pages_total or pages_selected
            document.route_page_index = snapshot.route_page_index
            document.route_pages_total = snapshot.route_pages_total
            document.pages_completed = snapshot.pages_completed
            document.pages_total = snapshot.pages_selected or pages_selected
            document.current_operation = snapshot.operation
            document.operation_id = snapshot.operation_id
            document.operation_status = snapshot.operation_status.value
            document.progress_kind = snapshot.progress_kind.value
            document.elapsed_seconds = snapshot.document_elapsed_seconds
            document.batch_elapsed_seconds = snapshot.batch_elapsed_seconds
            document.document_elapsed_seconds = snapshot.document_elapsed_seconds
            document.phase_elapsed_seconds = snapshot.phase_elapsed_seconds
            document.page_elapsed_seconds = snapshot.page_elapsed_seconds
            document.operation_elapsed_seconds = snapshot.operation_elapsed_seconds
            document.attempt_elapsed_seconds = snapshot.attempt_elapsed_seconds
            document.deadline_remaining_seconds = snapshot.deadline_remaining_seconds
            document.document_deadline_remaining_seconds = (
                snapshot.document_deadline_remaining_seconds
            )
            document.page_deadline_remaining_seconds = snapshot.page_deadline_remaining_seconds
            document.operation_deadline_remaining_seconds = (
                snapshot.operation_deadline_remaining_seconds
            )
            document.attempt_deadline_remaining_seconds = (
                snapshot.attempt_deadline_remaining_seconds
            )
            document.worker_generation = snapshot.worker_generation
            document.worker_restart_count = snapshot.worker_restart_count
            document.attempt_number = snapshot.attempt_number
            document.max_attempts = snapshot.max_attempts
            document.stage_timeline = list(snapshot.history[-32:])
            document.progress_version = progress_version
            document.server_timestamp = datetime.now(UTC)
            document.native_pages_retained = native_pages_retained
            document.native_pages_selected = native_pages_retained
            document.native_pages_completed = native_pages_retained
            document.embedded_ocr_pages_verified = embedded_ocr_pages_verified
            document.embedded_verification_pages_selected = (
                embedded_ocr_pages_verified + targeted_repair_pages_selected
            )
            document.embedded_verification_pages_completed = embedded_ocr_pages_verified
            document.targeted_repair_pages_selected = targeted_repair_pages_selected
            document.targeted_repair_pages_completed = targeted_repair_pages_completed
            document.full_ocr_pages_selected = full_ocr_pages_selected
            document.full_ocr_pages_completed = full_ocr_pages_completed
            document.full_ocr_pages_remaining = max(
                0, full_ocr_pages_selected - full_ocr_pages_completed
            )
            document.visual_no_text_pages = visual_no_text_pages
            document.failed_pages = failed_page_count
            document.pages_terminal_total = pages_completed
            document.pages_remaining = max(
                0, (document.pages_total or 0) - (document.pages_completed or 0)
            )
            document.estimate_status = eta_snap.estimate_status.value
            document.estimate_confidence = eta_snap.estimate_confidence
            document.estimate_sample_count = eta_snap.estimate_sample_count
            document.estimated_document_remaining_seconds = (
                eta_snap.estimated_document_remaining_seconds
            )
            document.estimated_queue_remaining_seconds = eta_snap.estimated_queue_remaining_seconds
            document.estimated_batch_remaining_seconds = eta_snap.estimated_queue_remaining_seconds
            document.estimated_completion_at = eta_snap.estimated_completion_at
            document.estimated_document_completion_at = eta_snap.estimated_completion_at
            document.estimated_batch_completion_at = eta_snap.estimated_completion_at
            document.estimated_current_operation_seconds = (
                eta_snap.estimated_current_operation_seconds
            )
            document.estimated_current_page_seconds = eta_snap.estimated_current_page_seconds
            document.average_page_seconds = eta_snap.average_page_seconds
            document.average_full_ocr_page_seconds = eta_snap.average_full_ocr_page_seconds
            document.pages_per_minute = eta_snap.pages_per_minute
            document.slow_warning_status = snapshot.slow_warning_status.value
            document.slow_warning_operation_id = snapshot.slow_warning_operation_id
            document.slow_warning_started_at = snapshot.slow_warning_started_at
            document.slow_warning_threshold_seconds = snapshot.slow_warning_threshold_seconds
            document.slow_warning_reason = snapshot.slow_warning_reason
            if snapshot.safe_message:
                document.user_status_message = snapshot.safe_message

        def _stamp_deadline(payload: dict[str, object]) -> None:
            doc_dl = payload.get("document_deadline_remaining_seconds")
            page_dl = payload.get("page_deadline_remaining_seconds")
            op_dl = payload.get("operation_deadline_remaining_seconds")
            attempt_dl = payload.get("attempt_deadline_remaining_seconds")
            legacy = payload.get("deadline_remaining_seconds")
            now = __import__("time").monotonic()
            if isinstance(doc_dl, (int, float)):
                snapshot.document_deadline_mono = now + float(doc_dl)
            if isinstance(page_dl, (int, float)):
                snapshot.page_deadline_mono = now + float(page_dl)
            elif page_dl is None and "page_deadline_remaining_seconds" in payload:
                snapshot.page_deadline_mono = None
            if isinstance(op_dl, (int, float)):
                snapshot.operation_deadline_mono = now + float(op_dl)
            if isinstance(attempt_dl, (int, float)):
                snapshot.attempt_deadline_mono = now + float(attempt_dl)
            # Legacy single field must not overwrite separated clocks when
            # explicit page/document deadlines are present.
            if (
                not isinstance(doc_dl, (int, float))
                and not isinstance(page_dl, (int, float))
                and isinstance(legacy, (int, float))
            ):
                snapshot.document_deadline_mono = now + float(legacy)
            snapshot._refresh_deadlines(now=now)

        def _begin_op(op: str, *, kind: ProgressKind = ProgressKind.DETERMINATE) -> None:
            snapshot.complete_open_operation(OperationStatus.COMPLETED)
            snapshot.progress_kind = kind
            accepted = snapshot.begin_operation(op)
            if not accepted and snapshot.last_lifecycle_reject is not None:
                log_progress(
                    "duplicate_event_prevented",
                    document_id=document.document_id,
                    job_id=job.job_id,
                    operation=op,
                    reason_code=snapshot.last_lifecycle_reject.value,
                )

        def _set_page_progress(page_number: int | None, page_pct: float) -> None:
            snapshot.set_visual_page_progress(
                pages_completed=pages_completed,
                pages_selected=pages_selected,
                page_number=page_number,
                page_percent=page_pct,
                include_page_in_fraction=True,
                selected_page_index=_selected_index_for(page_number),
                document_pages_total=page_count,
            )

        async def _publish_visual(
            event: ProgressEventType,
            *,
            page_number: int | None = None,
            reasons: list[str] | None = None,
            advance_version: bool = True,
        ) -> None:
            snapshot.mark_real_progress()
            _apply_snapshot(advance_version=advance_version)
            doc_page = page_number if page_number is not None else snapshot.document_page_number
            sel_idx = snapshot.selected_page_index or _selected_index_for(doc_page)
            await _safe_publish(
                session.broker,
                event,
                document_id=document.document_id,
                job_id=job.job_id,
                page_number=doc_page,
                pages_completed=pages_completed,
                pages_total=pages_selected,
                document_page_number=doc_page,
                document_pages_total=page_count,
                selected_page_index=sel_idx,
                selected_pages_total=pages_selected,
                visual_page_index=sel_idx,
                visual_pages_total=pages_selected,
                route_page_index=snapshot.route_page_index,
                route_pages_total=snapshot.route_pages_total,
                percent=document.progress_percent,
                overall_percent=snapshot.overall_percent,
                major_phase=snapshot.major_phase.value,
                major_phase_percent=snapshot.major_phase_percent,
                page_percent=snapshot.page_percent,
                operation=snapshot.operation,
                operation_id=snapshot.operation_id,
                operation_status=snapshot.operation_status.value,
                progress_kind=snapshot.progress_kind.value,
                elapsed_seconds=snapshot.document_elapsed_seconds,
                batch_elapsed_seconds=snapshot.batch_elapsed_seconds,
                document_elapsed_seconds=snapshot.document_elapsed_seconds,
                phase_elapsed_seconds=snapshot.phase_elapsed_seconds,
                page_elapsed_seconds=snapshot.page_elapsed_seconds,
                operation_elapsed_seconds=snapshot.operation_elapsed_seconds,
                attempt_elapsed_seconds=snapshot.attempt_elapsed_seconds,
                stage_elapsed_seconds=snapshot.operation_elapsed_seconds,
                deadline_remaining_seconds=snapshot.deadline_remaining_seconds,
                document_deadline_remaining_seconds=snapshot.document_deadline_remaining_seconds,
                page_deadline_remaining_seconds=snapshot.page_deadline_remaining_seconds,
                operation_deadline_remaining_seconds=snapshot.operation_deadline_remaining_seconds,
                attempt_deadline_remaining_seconds=snapshot.attempt_deadline_remaining_seconds,
                worker_generation=snapshot.worker_generation,
                worker_restart_count=snapshot.worker_restart_count,
                attempt_number=snapshot.attempt_number,
                max_attempts=snapshot.max_attempts,
                reason_codes=reasons,
                message=document.user_status_message,
                progress_version=document.progress_version,
                server_timestamp=document.server_timestamp,
                document_started_at=document.document_started_at,
                document_started_at_timestamp=document.document_started_at_timestamp,
                phase_started_at=document.phase_started_at,
                page_started_at=document.page_started_at,
                operation_started_at=document.operation_started_at,
                current_route=document.current_route,
                estimate_status=document.estimate_status,
                estimate_confidence=document.estimate_confidence,
                estimate_sample_count=document.estimate_sample_count,
                estimated_document_remaining_seconds=document.estimated_document_remaining_seconds,
                estimated_document_seconds_remaining=document.estimated_document_remaining_seconds,
                estimated_queue_remaining_seconds=document.estimated_queue_remaining_seconds,
                estimated_queue_seconds_remaining=document.estimated_queue_remaining_seconds,
                estimated_batch_remaining_seconds=document.estimated_batch_remaining_seconds,
                estimated_completion_at=document.estimated_completion_at,
                estimated_completion_time=document.estimated_completion_at,
                estimated_document_completion_at=document.estimated_document_completion_at,
                estimated_batch_completion_at=document.estimated_batch_completion_at,
                estimated_current_operation_seconds=document.estimated_current_operation_seconds,
                estimated_current_page_seconds=document.estimated_current_page_seconds,
                average_page_seconds=document.average_page_seconds,
                average_full_ocr_page_seconds=document.average_full_ocr_page_seconds,
                pages_per_minute=document.pages_per_minute,
                native_pages_retained=document.native_pages_retained,
                native_pages_selected=document.native_pages_selected,
                native_pages_completed=document.native_pages_completed,
                embedded_ocr_pages_verified=document.embedded_ocr_pages_verified,
                embedded_verification_pages_selected=document.embedded_verification_pages_selected,
                embedded_verification_pages_completed=document.embedded_verification_pages_completed,
                targeted_repair_pages_selected=document.targeted_repair_pages_selected,
                targeted_repair_pages_completed=document.targeted_repair_pages_completed,
                full_ocr_pages_selected=document.full_ocr_pages_selected,
                full_ocr_pages_completed=document.full_ocr_pages_completed,
                full_ocr_pages_remaining=document.full_ocr_pages_remaining,
                visual_no_text_pages=document.visual_no_text_pages,
                failed_pages=document.failed_pages,
                pages_terminal_total=document.pages_terminal_total,
                fair_scheduling_enabled=document.fair_scheduling_enabled,
                current_page=document.document_page_number,
                current_page_total=document.document_pages_total,
                current_operation=document.current_operation,
                slow_warning_status=document.slow_warning_status,
                slow_warning_operation_id=document.slow_warning_operation_id,
                slow_warning_started_at=document.slow_warning_started_at,
                slow_warning_threshold_seconds=document.slow_warning_threshold_seconds,
                slow_warning_reason=document.slow_warning_reason,
            )

        async def on_visual_progress(payload: dict[str, object]) -> None:
            nonlocal pages_completed, pages_selected, selection_started, selection_completed
            nonlocal native_pages_retained, embedded_ocr_pages_verified
            nonlocal targeted_repair_pages_selected, targeted_repair_pages_completed
            nonlocal full_ocr_pages_selected, full_ocr_pages_completed
            nonlocal visual_no_text_pages, failed_page_count, selected_page_numbers
            event_type = str(payload.get("type", ""))
            raw_page = payload.get("page_number")
            page_number = int(raw_page) if isinstance(raw_page, (int, float, str)) else None
            attempt_number = payload.get("attempt_number")
            if isinstance(attempt_number, int):
                snapshot.attempt_number = attempt_number
            max_attempts = payload.get("max_attempts")
            if isinstance(max_attempts, int):
                snapshot.max_attempts = max_attempts
            worker_generation = payload.get("worker_generation")
            if isinstance(worker_generation, int):
                snapshot.worker_generation = worker_generation
            worker_restart_count = payload.get("worker_restart_count")
            if isinstance(worker_restart_count, int):
                snapshot.worker_restart_count = worker_restart_count
            worker_pid = payload.get("pid")
            if isinstance(worker_pid, int):
                snapshot.worker_pid = worker_pid
            _stamp_deadline(payload)

            if event_type == "worker.heartbeat":
                snapshot.progress_kind = ProgressKind.HEARTBEAT
                if snapshot.operation_is_open:
                    snapshot.operation_status = OperationStatus.HEARTBEAT
                snapshot.mark_heartbeat()
                document.user_status_message = (
                    f"OCR in progress ({snapshot.operation.replace('_', ' ')})"
                )
                _apply_snapshot(advance_version=False)
                log_progress(
                    "visual_heartbeat",
                    document_id=document.document_id,
                    job_id=job.job_id,
                    overall_percent=snapshot.overall_percent,
                    major_phase=snapshot.major_phase.value,
                    major_phase_percent=snapshot.major_phase_percent,
                    document_page_number=page_number or snapshot.document_page_number,
                    document_pages_total=page_count,
                    selected_page_index=snapshot.selected_page_index,
                    selected_pages_total=pages_selected,
                    page_percent=snapshot.page_percent,
                    operation=snapshot.operation,
                    operation_id=snapshot.operation_id,
                    operation_status="heartbeat",
                    progress_kind="heartbeat",
                    elapsed_seconds=snapshot.document_elapsed_seconds,
                    document_elapsed_seconds=snapshot.document_elapsed_seconds,
                    page_elapsed_seconds=snapshot.page_elapsed_seconds,
                    operation_elapsed_seconds=snapshot.operation_elapsed_seconds,
                    document_deadline_remaining_seconds=(
                        snapshot.document_deadline_remaining_seconds
                    ),
                    page_deadline_remaining_seconds=snapshot.page_deadline_remaining_seconds,
                    worker_pid=snapshot.worker_pid,
                    worker_generation=snapshot.worker_generation,
                    attempt_number=snapshot.attempt_number,
                    max_attempts=snapshot.max_attempts,
                    slow_warning_status=snapshot.slow_warning_status.value,
                )
                return

            publish_event: ProgressEventType | None = None
            reasons_raw = payload.get("reason_codes")
            reasons = [str(item) for item in reasons_raw] if isinstance(reasons_raw, list) else None

            if event_type == "visual_pages_selected":
                if selection_completed:
                    log_progress(
                        "duplicate_event_prevented",
                        document_id=document.document_id,
                        job_id=job.job_id,
                        operation="visual_page_selection",
                        reason_code="duplicate_selection",
                    )
                    return
                if not selection_started:
                    selection_started = True
                    _begin_op("visual_page_selection")
                    document.user_status_message = "Selecting pages for printed OCR"
                raw_selected = payload.get("pages_selected")
                page_numbers = payload.get("page_numbers")
                if isinstance(page_numbers, list):
                    selected_page_numbers = [
                        int(p) for p in page_numbers if isinstance(p, (int, float, str))
                    ]
                    pages_selected = len(selected_page_numbers)
                elif isinstance(raw_selected, (int, float)):
                    pages_selected = max(0, int(raw_selected))
                selection_completed = True
                snapshot.set_visual_selection_complete(pages_selected=pages_selected)
                snapshot.terminal_operation(OperationStatus.COMPLETED)
                document.user_status_message = "Visual pages selected"
                for key in (
                    "native_pages_retained",
                    "embedded_ocr_pages_verified",
                    "targeted_repair_pages_selected",
                    "full_ocr_pages_selected",
                ):
                    raw = payload.get(key)
                    if not isinstance(raw, (int, float)):
                        continue
                    value = int(raw)
                    if key == "native_pages_retained":
                        native_pages_retained = value
                    elif key == "embedded_ocr_pages_verified":
                        embedded_ocr_pages_verified = value
                    elif key == "targeted_repair_pages_selected":
                        targeted_repair_pages_selected = value
                    elif key == "full_ocr_pages_selected":
                        full_ocr_pages_selected = value
                publish_event = ProgressEventType.DOCUMENT_VISUAL_PAGES_SELECTED

            elif event_type == "page_route_started":
                document.page_started_at = datetime.now(UTC)
                publish_event = ProgressEventType.DOCUMENT_PAGE_ROUTE_STARTED

            elif event_type == "page_route_completed":
                route = payload.get("route")
                if isinstance(route, str):
                    document.current_route = route
                    if route == PageRoute.DIGITAL_NATIVE.value:
                        eta.record(EtaCostRoute.DIGITAL_NATIVE, 0.05)
                    elif route == PageRoute.EMBEDDED_OCR_VERIFIED.value:
                        eta.record(EtaCostRoute.EMBEDDED_OCR_VISUAL_CHECK, 0.4)
                    elif route == PageRoute.FULL_VISUAL_OCR.value:
                        pass
                publish_event = ProgressEventType.DOCUMENT_PAGE_ROUTE_COMPLETED

            elif event_type == "embedded_ocr_verified":
                publish_event = ProgressEventType.DOCUMENT_EMBEDDED_OCR_VERIFIED

            elif event_type == "embedded_ocr_targeted_repair_started":
                publish_event = ProgressEventType.DOCUMENT_EMBEDDED_OCR_TARGETED_REPAIR_STARTED

            elif event_type == "visual_no_text_completed":
                pages_completed += 1
                publish_event = ProgressEventType.DOCUMENT_VISUAL_NO_TEXT_COMPLETED

            elif event_type == "full_ocr_primary_started":
                _begin_op("full_ocr_primary", kind=ProgressKind.INDETERMINATE)
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_PRIMARY_STARTED

            elif event_type == "full_ocr_primary_completed":
                if (
                    snapshot.operation == "full_ocr_primary"
                    and snapshot.operation_status is OperationStatus.COMPLETED
                ):
                    log_progress(
                        "duplicate_event_prevented",
                        document_id=document.document_id,
                        job_id=job.job_id,
                        operation="full_ocr_primary",
                        reason_code="duplicate_terminal",
                    )
                    return
                duration_ms = payload.get("primary_duration_ms")
                if isinstance(duration_ms, (int, float)):
                    eta.record(EtaCostRoute.FULL_OCR_PRIMARY, float(duration_ms) / 1000.0)
                if not snapshot.terminal_operation(OperationStatus.COMPLETED):
                    log_progress(
                        "duplicate_event_prevented",
                        document_id=document.document_id,
                        job_id=job.job_id,
                        operation="full_ocr_primary",
                        reason_code=(
                            snapshot.last_lifecycle_reject.value
                            if snapshot.last_lifecycle_reject
                            else "duplicate_terminal"
                        ),
                    )
                    return
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_PRIMARY_COMPLETED

            elif event_type == "full_ocr_quality_evaluation_started":
                _begin_op("full_ocr_quality_evaluation", kind=ProgressKind.INDETERMINATE)
                document.user_status_message = "Evaluating primary OCR quality"
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_QUALITY_EVALUATION_STARTED

            elif event_type == "full_ocr_quality_evaluation_completed":
                snapshot.terminal_operation(OperationStatus.COMPLETED)
                raw_fallback_reasons = payload.get("fallback_reason_codes")
                fallback_reasons: list[str] = (
                    [str(r) for r in raw_fallback_reasons]
                    if isinstance(raw_fallback_reasons, list)
                    else []
                )
                if payload.get("fallback_recommended"):
                    reason_txt = (
                        "Dense-form output was too fragmented"
                        if "excessive_fragmentation" in fallback_reasons
                        or "dense_form_fragmentation" in fallback_reasons
                        else "Primary OCR quality gate failed"
                    )
                    document.user_status_message = f"Fallback reason: {reason_txt}"
                else:
                    document.user_status_message = "Primary OCR quality accepted"
                quality_page = payload.get("page_number")
                log_progress(
                    "ocr_quality_evaluated",
                    document_id=document.document_id,
                    page_number=int(quality_page) if isinstance(quality_page, int) else None,
                    page_profile=payload.get("page_profile"),
                    quality_policy_version=payload.get("quality_policy_version"),
                    primary_limit_side=payload.get("primary_limit_side"),
                    primary_quality_status=payload.get("primary_quality_status"),
                    primary_fragmentation_score=payload.get("primary_fragmentation_score"),
                    primary_low_confidence_ratio=payload.get("primary_low_confidence_ratio"),
                    primary_symbol_ratio=payload.get("primary_symbol_ratio"),
                    fallback_triggered=bool(payload.get("fallback_recommended")),
                    fallback_reason_codes=fallback_reasons,
                )
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_QUALITY_EVALUATION_COMPLETED

            elif event_type == "full_ocr_fallback_started":
                _begin_op("full_ocr_fallback", kind=ProgressKind.INDETERMINATE)
                document.user_status_message = "Running high-resolution OCR fallback"
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_FALLBACK_STARTED

            elif event_type == "full_ocr_fallback_completed":
                duration_ms = payload.get("fallback_duration_ms")
                if isinstance(duration_ms, (int, float)):
                    eta.record(EtaCostRoute.FULL_OCR_FALLBACK, float(duration_ms) / 1000.0)
                snapshot.terminal_operation(OperationStatus.COMPLETED)
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_FALLBACK_COMPLETED

            elif event_type == "full_ocr_result_selection_started":
                _begin_op("full_ocr_result_selection", kind=ProgressKind.INDETERMINATE)
                document.user_status_message = "Selecting the best OCR result"
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_RESULT_SELECTION_STARTED

            elif event_type == "full_ocr_result_selection_completed":
                snapshot.terminal_operation(OperationStatus.COMPLETED)
                selected = payload.get("selected_pass") or "primary"
                document.user_status_message = f"Selected OCR pass: {selected}"
                selection_page = payload.get("page_number")
                raw_sel = payload.get("selection_reason_codes")
                selection_reasons = [str(r) for r in raw_sel] if isinstance(raw_sel, list) else []
                log_progress(
                    "ocr_quality_evaluated",
                    document_id=document.document_id,
                    page_number=int(selection_page) if isinstance(selection_page, int) else None,
                    selected_pass=selected,
                    selection_reason_codes=selection_reasons,
                    primary_limit_side=payload.get("primary_limit_side"),
                    fallback_limit_side=payload.get("fallback_limit_side"),
                    fallback_triggered=bool(payload.get("fallback_triggered")),
                )
                publish_event = ProgressEventType.DOCUMENT_FULL_OCR_RESULT_SELECTION_COMPLETED

            elif event_type == "operation_skipped":
                snapshot.complete_open_operation(OperationStatus.SKIPPED)
                if snapshot.operation_status is not OperationStatus.SKIPPED:
                    snapshot.begin_operation("operation_skipped", status=OperationStatus.STARTED)
                    snapshot.terminal_operation(
                        OperationStatus.SKIPPED,
                        allow_skip_without_start=True,
                    )
                document.user_status_message = "Skipped full visual OCR (trusted native text)"
                _apply_snapshot()
                return

            elif event_type == "worker.request":
                # Do not re-start visual_page_selection; selection is owned by
                # visual_pages_selected. Worker request is diagnostic only.
                if not selection_completed:
                    snapshot.bump_overall(OVERALL_VISUAL_SELECT_END)
                document.user_status_message = "Dispatching printed OCR request"
                _apply_snapshot(advance_version=False)
                log_progress(
                    "visual_progress",
                    document_id=document.document_id,
                    job_id=job.job_id,
                    overall_percent=snapshot.overall_percent,
                    operation="worker_request",
                    operation_status="started",
                    pages_completed=pages_completed,
                    selected_pages_total=pages_selected,
                )
                return

            elif event_type in {
                "native_visibility_started",
                "native_visibility_supported",
                "native_visibility_rejected",
                "native_visibility_skipped",
            }:
                snapshot.set_visual_visibility_complete()
                document.user_status_message = "Native visibility evaluated"
                publish_event = {
                    "native_visibility_started": (
                        ProgressEventType.DOCUMENT_NATIVE_VISIBILITY_STARTED
                    ),
                    "native_visibility_supported": (
                        ProgressEventType.DOCUMENT_NATIVE_VISIBILITY_SUPPORTED
                    ),
                    "native_visibility_rejected": (
                        ProgressEventType.DOCUMENT_NATIVE_VISIBILITY_REJECTED
                    ),
                }.get(event_type)

            elif event_type == "worker.retry":
                snapshot.complete_open_operation(OperationStatus.FAILED)
                snapshot.attempt_number = snapshot.attempt_number + 1
                _begin_op("worker_retry")
                snapshot.operation_status = OperationStatus.RETRYING
                document.user_status_message = (
                    f"Retrying after OCR worker restart "
                    f"(attempt {snapshot.attempt_number} of {snapshot.max_attempts})"
                )

            elif event_type == "page.started":
                sel_idx = _selected_index_for(page_number)
                if page_number is not None:
                    snapshot.begin_page(
                        page_number,
                        selected_page_index=sel_idx,
                        selected_pages_total=pages_selected,
                        visual_page_index=sel_idx,
                        visual_pages_total=pages_selected,
                    )
                    document.page_started_at = datetime.now(UTC)
                    document.operation_started_at = document.page_started_at
                _begin_op("visual_page_render")
                _set_page_progress(page_number, PAGE_QUEUED)
                document.user_status_message = (
                    f"Rendering {_page_label(page_number)}" if page_number else "Rendering page"
                )
                publish_event = ProgressEventType.DOCUMENT_VISUAL_PAGE_STARTED

            elif event_type == "page.rendered":
                snapshot.complete_open_operation(OperationStatus.COMPLETED)
                _begin_op("visual_preprocessing")
                _set_page_progress(page_number, PAGE_RENDERED)
                document.user_status_message = (
                    f"Rendered {_page_label(page_number)}" if page_number else "Page rendered"
                )
                publish_event = ProgressEventType.DOCUMENT_VISUAL_PAGE_RENDERED

            elif event_type == "page.ocr_started":
                snapshot.complete_open_operation(OperationStatus.COMPLETED)
                _begin_op("paddle_ocr_pipeline", kind=ProgressKind.INDETERMINATE)
                _set_page_progress(page_number, PAGE_PREPROCESSED)
                document.user_status_message = (
                    f"Recognising {_page_label(page_number)}"
                    if page_number
                    else "Recognising printed text"
                )
                publish_event = ProgressEventType.DOCUMENT_VISUAL_PAGE_OCR_STARTED

            elif event_type == "page.ocr_completed":
                if snapshot.operation == "paddle_ocr_pipeline" and snapshot.operation_is_open:
                    snapshot.progress_kind = ProgressKind.DETERMINATE
                    _set_page_progress(page_number, PAGE_OCR_PIPELINE_DONE)
                    snapshot.terminal_operation(OperationStatus.COMPLETED)
                else:
                    _set_page_progress(page_number, PAGE_OCR_PIPELINE_DONE)

            elif event_type == "page.mapping_started":
                _begin_op("visual_coordinate_mapping")
                document.user_status_message = (
                    f"Mapping coordinates on page {page_number}"
                    if page_number
                    else "Mapping coordinates"
                )

            elif event_type == "page.mapping_completed":
                if snapshot.operation == "visual_coordinate_mapping":
                    _set_page_progress(page_number, PAGE_MAPPING_DONE)
                    snapshot.terminal_operation(OperationStatus.COMPLETED)

            elif event_type == "page.grouping_started":
                _begin_op("visual_line_grouping")
                document.user_status_message = (
                    f"Grouping lines on page {page_number}" if page_number else "Grouping lines"
                )

            elif event_type == "page.grouping_completed":
                if snapshot.operation == "visual_line_grouping":
                    _set_page_progress(page_number, PAGE_GROUPED)
                    snapshot.terminal_operation(OperationStatus.COMPLETED)

            elif event_type == "page.completed":
                snapshot.complete_open_operation(OperationStatus.COMPLETED)
                _begin_op("visual_page_publication")
                # Page at 100% while still counting prior completed pages only.
                snapshot.set_visual_page_progress(
                    pages_completed=pages_completed,
                    pages_selected=pages_selected,
                    page_number=page_number,
                    page_percent=PAGE_PUBLISHED,
                    include_page_in_fraction=True,
                    selected_page_index=_selected_index_for(page_number),
                    document_pages_total=page_count,
                )
                snapshot.terminal_operation(OperationStatus.COMPLETED)
                pages_completed += 1
                full_ocr_pages_completed += 1
                # After publish: finished pages counted once; no double-count.
                snapshot.set_visual_page_progress(
                    pages_completed=pages_completed,
                    pages_selected=pages_selected,
                    page_number=page_number,
                    page_percent=PAGE_PUBLISHED,
                    include_page_in_fraction=False,
                    selected_page_index=_selected_index_for(page_number),
                    document_pages_total=page_count,
                )
                document.user_status_message = (
                    f"Published {_page_label(page_number)}" if page_number else "Published page"
                )
                status = str(payload.get("status", ""))
                if status == "completed_no_text":
                    visual_no_text_pages += 1
                    publish_event = ProgressEventType.DOCUMENT_VISUAL_PAGE_NO_TEXT
                else:
                    publish_event = ProgressEventType.DOCUMENT_VISUAL_PAGE_OCR_COMPLETED

            elif event_type == "page.failed":
                snapshot.complete_open_operation(OperationStatus.FAILED)
                _begin_op("visual_page_publication")
                snapshot.set_visual_page_progress(
                    pages_completed=pages_completed,
                    pages_selected=pages_selected,
                    page_number=page_number,
                    page_percent=PAGE_PUBLISHED,
                    include_page_in_fraction=True,
                    selected_page_index=_selected_index_for(page_number),
                    document_pages_total=page_count,
                )
                reason = payload.get("reason_code") or payload.get("code")
                timed_out = str(reason or "").endswith("timeout") or "timeout" in str(
                    payload.get("message") or ""
                )
                terminal = OperationStatus.TIMED_OUT if timed_out else OperationStatus.FAILED
                snapshot.terminal_operation(
                    terminal,
                    reason_code=str(reason) if reason else None,
                )
                pages_completed += 1
                failed_page_count += 1
                snapshot.set_visual_page_progress(
                    pages_completed=pages_completed,
                    pages_selected=pages_selected,
                    page_number=page_number,
                    page_percent=PAGE_PUBLISHED,
                    include_page_in_fraction=False,
                    selected_page_index=_selected_index_for(page_number),
                    document_pages_total=page_count,
                )
                document.user_status_message = (
                    f"Page {page_number} failed" if page_number else "Visual page failed"
                )
                publish_event = ProgressEventType.DOCUMENT_VISUAL_PAGE_FAILED
                if reason:
                    reasons = [str(reason)]

            elif event_type == "visual_summary_publication.started":
                _begin_op("visual_summary_publication")
                snapshot.set_visual_summary_progress()
                document.user_status_message = "Publishing visual summary"

            elif event_type == "visual_summary_publication.completed":
                if snapshot.operation == "visual_summary_publication":
                    snapshot.terminal_operation(OperationStatus.COMPLETED)
                snapshot.set_visual_summary_progress()
                document.user_status_message = "Visual summary published"

            elif event_type == "visual_authority_reconciliation.started":
                _begin_op("visual_authority_reconciliation")
                snapshot.set_visual_authority_progress()
                document.user_status_message = "Reconciling document authority"

            elif event_type == "visual_authority_reconciliation.completed":
                if snapshot.operation == "visual_authority_reconciliation":
                    snapshot.terminal_operation(OperationStatus.COMPLETED)
                snapshot.set_visual_authority_progress()
                document.user_status_message = "Document authority reconciled"

            else:
                return

            snapshot.safe_message = document.user_status_message
            _apply_snapshot()
            log_progress(
                "visual_progress",
                document_id=document.document_id,
                job_id=job.job_id,
                overall_percent=snapshot.overall_percent,
                major_phase=snapshot.major_phase.value,
                major_phase_percent=snapshot.major_phase_percent,
                page_number=page_number,
                pages_total=pages_selected,
                pages_completed=pages_completed,
                page_percent=snapshot.page_percent,
                operation=snapshot.operation,
                operation_status=snapshot.operation_status.value,
                progress_kind=snapshot.progress_kind.value,
                elapsed_seconds=snapshot.document_elapsed_seconds,
                document_elapsed_seconds=snapshot.document_elapsed_seconds,
                page_elapsed_seconds=snapshot.page_elapsed_seconds,
                operation_elapsed_seconds=snapshot.operation_elapsed_seconds,
                deadline_remaining_seconds=snapshot.deadline_remaining_seconds,
                worker_pid=snapshot.worker_pid,
                worker_generation=snapshot.worker_generation,
                worker_restart_count=snapshot.worker_restart_count,
                attempt_number=snapshot.attempt_number,
                max_attempts=snapshot.max_attempts,
                reason_code=snapshot.reason_code,
            )
            if publish_event is not None:
                await _publish_visual(publish_event, page_number=page_number, reasons=reasons)

        canonical_pdf = self._file_store.canonical_path(session.session_id, document.document_id)
        try:
            summary = await self._visual.process_document(
                session_id=session.session_id,
                document_id=document.document_id,
                job_id=job.job_id,
                canonical_pdf=canonical_pdf,
                canonical_pages=document.canonical_pages,
                native_summary=native_summary,  # type: ignore[arg-type]
                native_pages=native_pages,
                cancel_token=job.cancellation,
                on_progress=on_visual_progress,
            )
        except JobCancelledError:
            raise
        except VisualOcrError as exc:
            had_native = bool(document.native_result_available)
            document.status = (
                DocumentStatus.VISUAL_PROCESSING_PARTIAL
                if had_native
                else DocumentStatus.VISUAL_PROCESSING_FAILED
            )
            document.progress_percent = _MAX_PROGRESS_PERCENT
            document.failure_stage = exc.operation or "paddle_ocr_pipeline"
            document.failure_code = exc.code.value
            document.failure_message = (
                "OCR page timed out"
                if exc.code.value == "ocr_page_timeout"
                else "The OCR service failed to process this document."
            )
            document.current_operation = document.failure_stage
            document.operation_status = "failed"
            document.user_status_message = "Visual OCR could not complete."
            document.visual_processing_performed = True
            document.visual_result_available = False
            document.major_phase = "visual_ocr"
            document.major_phase_percent = 100.0
            logger.exception(
                "Visual OCR failed exception_type=%s safe_error_code=%s "
                "failing_component=%s failing_operation=%s",
                type(exc).__name__,
                exc.code.value,
                getattr(exc, "failing_component", None) or "VisualOcrService",
                exc.operation or "paddle_ocr_pipeline",
                extra={
                    "document_id": document.document_id,
                    "job_id": job.job_id,
                    "page_number": getattr(exc, "page_number", None) or document.active_page_number,
                    "exception_type": type(exc).__name__,
                    "safe_error_code": exc.code.value,
                    "failing_component": getattr(exc, "failing_component", None)
                    or "VisualOcrService",
                    "failing_operation": exc.operation or "paddle_ocr_pipeline",
                    "visual_page_count": document.canonical_page_count,
                    "selected_page_count": document.pages_total,
                    "worker_generation": document.worker_generation,
                    "attempt_number": document.attempt_number,
                },
            )
            if self._visual is not None:
                try:
                    from backend.app.contracts.visual import VisualProcessingStatus

                    self._visual.publish_terminal_failure_summary(
                        session_id=session.session_id,
                        document_id=document.document_id,
                        page_count=document.canonical_page_count or 0,
                        error_code=exc.code.value,
                        canonical_document_available=document.canonical_view_available,
                        native_pages_retained=(
                            document.canonical_page_count or 0 if had_native else 0
                        ),
                        pages_selected=document.pages_total or 0,
                        status=(
                            VisualProcessingStatus.VISUAL_PROCESSING_PARTIAL
                            if had_native
                            else VisualProcessingStatus.VISUAL_PROCESSING_FAILED
                        ),
                        user_status_message=document.user_status_message
                        or document.failure_message,
                    )
                except Exception:
                    logger.exception(
                        "Visual terminal summary publication failed",
                        extra={
                            "document_id": document.document_id,
                            "job_id": job.job_id,
                            "exception_type": "SummaryPublishError",
                            "safe_error_code": ErrorCode.VISUAL_RESULT_PUBLISH_FAILED.value,
                            "failing_component": "VisualOcrService",
                            "failing_operation": "visual_summary_publication",
                        },
                    )
            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_VISUAL_PROCESSING_FAILED
                if not had_native
                else ProgressEventType.DOCUMENT_VISUAL_PROCESSING_PARTIAL,
                document_id=document.document_id,
                job_id=job.job_id,
                percent=_MAX_PROGRESS_PERCENT,
                document_status=document.status,
                message=document.user_status_message,
                reason_codes=[exc.code.value],
            )
            return

        # Persist visibility downgrades onto published native results so public
        # APIs (including summary.page_decisions used by smoke) never keep
        # suppressed native authority after Phase 4.
        await on_visual_progress({"type": "visual_authority_reconciliation.started"})
        downgraded_any = False
        for page in native_pages.values():
            phase4_visibility = (
                page.trust.visual_agreement_status.value == "evaluated_phase_4_visibility"
            )
            visibility_reason = (
                "native_text_not_visually_present" in page.trust.reason_codes
                or "native_text_visibility_uncertain" in page.trust.reason_codes
            )
            if (
                phase4_visibility
                and page.trust.visual_processing_required
                and not page.trust.native_result_available
                and (page.decision is NativePageDecision.REJECTED or visibility_reason)
            ):
                self._native.republish_page(session.session_id, document.document_id, page)
                downgraded_any = True

        if downgraded_any or summary.native_pages_downgraded > 0:
            document.native_result_available = False
            document.visual_processing_required = True
            existing_summary = self._native.load_summary(session.session_id, document.document_id)
            if existing_summary is not None:
                by_number = {entry.page_number: entry for entry in existing_summary.page_decisions}
                for page_number, page in native_pages.items():
                    by_number[page_number] = page.trust
                decisions = [by_number[n] for n in sorted(by_number)]
                accepted = sum(1 for d in decisions if d.decision is NativePageDecision.ACCEPTED)
                rejected = sum(1 for d in decisions if d.decision is NativePageDecision.REJECTED)
                absent = sum(1 for d in decisions if d.decision is NativePageDecision.ABSENT)
                errored = sum(1 for d in decisions if d.decision is NativePageDecision.ERROR)
                suppressed = sum(
                    1
                    for d in decisions
                    if d.decision is NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION
                )
                updated = existing_summary.model_copy(
                    update={
                        "document_source_policy": summary.document_source_policy
                        or existing_summary.document_source_policy,
                        "native_result_available": False,
                        "visual_processing_required": True,
                        "page_decisions": decisions,
                        "pages_accepted": accepted,
                        "pages_rejected": rejected,
                        "pages_absent": absent,
                        "pages_errored": errored,
                        "pages_suppressed": suppressed,
                    }
                )
                self._native.republish_summary(session.session_id, document.document_id, updated)
        await on_visual_progress({"type": "visual_authority_reconciliation.completed"})

        from backend.app.contracts.visual import VisualProcessingStatus

        if summary.visual_processing_status is VisualProcessingStatus.VISUAL_PROCESSING_PARTIAL:
            document.status = DocumentStatus.VISUAL_PROCESSING_PARTIAL
            complete_event = ProgressEventType.DOCUMENT_VISUAL_PROCESSING_PARTIAL
        elif summary.visual_processing_status is VisualProcessingStatus.VISUAL_PROCESSING_FAILED:
            document.status = DocumentStatus.VISUAL_PROCESSING_FAILED
            complete_event = ProgressEventType.DOCUMENT_VISUAL_PROCESSING_FAILED
            failed_pages = [p for p in summary.page_summaries if p.error_code]
            if failed_pages:
                first = failed_pages[0]
                document.failure_code = first.error_code
                document.failure_page_number = first.page_number
                document.failure_stage = (
                    "paddle_ocr_pipeline"
                    if first.error_code == "ocr_page_timeout"
                    else _VISUAL_STAGE
                )
                document.failure_message = (
                    "OCR page timed out"
                    if first.error_code == "ocr_page_timeout"
                    else "Printed visual OCR failed."
                )
                document.user_status_message = "Visual OCR could not complete."
                document.current_operation = document.failure_stage
            document.attempt_number = snapshot.attempt_number
            document.max_attempts = snapshot.max_attempts
        else:
            document.status = DocumentStatus.VISUAL_PROCESSING_COMPLETE
            complete_event = ProgressEventType.DOCUMENT_VISUAL_PROCESSING_COMPLETED

        snapshot.set_visual_complete()
        snapshot.complete_open_operation(OperationStatus.COMPLETED)
        document.progress_percent = _MAX_PROGRESS_PERCENT
        document.visual_processing_performed = True
        document.visual_result_available = summary.visual_result_available
        document.visual_processing_required = summary.pages_selected > 0
        if summary.document_source_policy is not None:
            document.document_source_policy = summary.document_source_policy
        document.user_status_message = summary.user_status_message or _PHASE4_COMPLETE_MESSAGE
        document.pages_completed = summary.pages_completed
        document.pages_total = summary.pages_selected or summary.page_count
        document.major_phase = MajorPhase.VISUAL_OCR.value
        document.major_phase_percent = 100.0
        document.operation_status = OperationStatus.COMPLETED.value
        document.current_operation = "visual_processing_complete"
        _apply_snapshot()

        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_VISUAL_GROUPING_COMPLETED,
            document_id=document.document_id,
            job_id=job.job_id,
            percent=_VISUAL_GROUP_PROGRESS,
            overall_percent=snapshot.overall_percent,
            major_phase=snapshot.major_phase.value,
            major_phase_percent=snapshot.major_phase_percent,
            operation=snapshot.operation,
            operation_status=snapshot.operation_status.value,
        )
        await _safe_publish(
            session.broker,
            complete_event,
            document_id=document.document_id,
            job_id=job.job_id,
            percent=_MAX_PROGRESS_PERCENT,
            overall_percent=OVERALL_CAP,
            major_phase=MajorPhase.VISUAL_OCR.value,
            major_phase_percent=100.0,
            document_status=document.status,
            pages_completed=document.pages_completed,
            pages_total=document.pages_total,
            operation="visual_processing_complete",
            operation_status=OperationStatus.COMPLETED.value,
            message=document.user_status_message,
        )

    async def _finalize_native_failed(
        self,
        session: RuntimeSession,
        job: ProcessingJob,
        document: RuntimeDocument,
        *,
        code: str,
        page_number: int | None = None,
        operation: str | None = None,
    ) -> None:
        infra_codes = {
            ErrorCode.NATIVE_WORKER_START_FAILED.value,
            ErrorCode.NATIVE_WORKER_NOT_CONFIGURED.value,
            ErrorCode.NATIVE_WORKER_FAILED.value,
            ErrorCode.NATIVE_WORKER_OUTPUT_INVALID.value,
            ErrorCode.NATIVE_RESULT_PUBLISH_FAILED.value,
            ErrorCode.NATIVE_EXTRACTION_TIMEOUT.value,
            ErrorCode.NATIVE_EXTRACTION_FAILED.value,
        }
        safe_message = (
            "Native processing could not start or publish its result."
            if code in infra_codes
            else (
                "Native text processing could not read the embedded text on one or more "
                "pages. The canonical document is still available and visual processing "
                "is required."
            )
        )
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(UTC)
        job.failure_code = code
        job.failure_message = safe_message
        document.status = DocumentStatus.FAILED
        document.native_extraction_performed = False
        document.native_result_available = False
        document.visual_processing_required = True
        document.failure_stage = "extracting_native"
        document.failure_code = code
        document.failure_message = safe_message
        document.failure_page_number = page_number
        document.user_status_message = safe_message
        if operation:
            # Keep operation out of user message; available in structured logs only.
            pass
        self._native.cleanup_staging(session.session_id, job.job_id)
        self._native.delete_results(session.session_id, document.document_id)
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_NATIVE_EXTRACTION_FAILED,
            document_id=document.document_id,
            job_id=job.job_id,
            message=job.failure_message,
            document_status=DocumentStatus.FAILED,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_FAILED,
            document_id=document.document_id,
            job_id=job.job_id,
            message=job.failure_message,
            document_status=DocumentStatus.FAILED,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.JOB_FAILED,
            document_id=document.document_id,
            job_id=job.job_id,
            job_status=JobStatus.FAILED,
            message=job.failure_message,
        )

    @staticmethod
    def _finalize_orphan(job: ProcessingJob) -> None:
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)

    async def _finalize_cancelled(
        self, session: RuntimeSession, job: ProcessingJob, document: RuntimeDocument
    ) -> None:
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
        had_canonical = document.canonical_view_available
        document.status = DocumentStatus.CANCELLED
        if not had_canonical:
            document.canonical_status = CanonicalStatus.CANCELLED
            document.canonical_view_available = False
        self._file_store.remove_file(
            self._file_store.canonical_part_path(session.session_id, document.document_id)
        )
        self._native.cleanup_staging(session.session_id, job.job_id)
        self._native.delete_results(session.session_id, document.document_id)
        document.native_extraction_performed = False
        document.native_result_available = False
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_CANONICALISATION_CANCELLED,
            document_id=document.document_id,
            job_id=job.job_id,
            document_status=DocumentStatus.CANCELLED,
            canonical_status=(
                document.canonical_status.value
                if document.canonical_status is not None
                else CanonicalStatus.CANCELLED.value
            ),
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_CANCELLED,
            document_id=document.document_id,
            job_id=job.job_id,
            document_status=DocumentStatus.CANCELLED,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.JOB_CANCELLED,
            document_id=document.document_id,
            job_id=job.job_id,
            job_status=JobStatus.CANCELLED,
        )

    async def _finalize_failed(
        self,
        session: RuntimeSession,
        job: ProcessingJob,
        document: RuntimeDocument,
        *,
        code: str = _FAILURE_CODE,
    ) -> None:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(UTC)
        job.failure_code = code
        job.failure_message = "Canonicalisation could not be completed."
        document.status = DocumentStatus.FAILED
        document.canonical_status = CanonicalStatus.FAILED
        document.canonical_view_available = False
        document.canonical_failure_code = code
        self._file_store.remove_file(
            self._file_store.canonical_part_path(session.session_id, document.document_id)
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_CANONICALISATION_FAILED,
            document_id=document.document_id,
            job_id=job.job_id,
            message=job.failure_message,
            document_status=DocumentStatus.FAILED,
            canonical_status=CanonicalStatus.FAILED.value,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.DOCUMENT_FAILED,
            document_id=document.document_id,
            job_id=job.job_id,
            message=job.failure_message,
            document_status=DocumentStatus.FAILED,
        )
        await _safe_publish(
            session.broker,
            ProgressEventType.JOB_FAILED,
            document_id=document.document_id,
            job_id=job.job_id,
            message=job.failure_message,
            job_status=JobStatus.FAILED,
        )
