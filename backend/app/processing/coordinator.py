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
from backend.app.contracts.native import NativePageDecision
from backend.app.contracts.processing import IgnoredDocument
from backend.app.contracts.progress import ProgressEventType
from backend.app.extraction.native.errors import NativeExtractionError
from backend.app.extraction.native.service import NativeExtractionService
from backend.app.observability.errors import ApiException
from backend.app.processing.cancellation import JobCancelledError
from backend.app.processing.models import ProcessingJob
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
_MAX_CANONICAL_PROGRESS = 15
_NATIVE_INSPECT_PROGRESS = 16
_NATIVE_PAGE_START = 20
_NATIVE_PAGE_END = 32
_NATIVE_POLICY_PROGRESS = 34
_MAX_PROGRESS_PERCENT = 35
_PROGRESS_STARTED = 6


async def _safe_publish(broker: EventBroker, event: ProgressEventType, **fields: object) -> None:
    with contextlib.suppress(BrokerClosedError):
        await broker.publish(event, **fields)  # type: ignore[arg-type]


class ProcessingCoordinator:
    """Coordinates canonicalisation and native extraction with one worker."""

    def __init__(
        self,
        registry: SessionRegistry,
        job_queue: JobQueue,
        processor: CanonicalisationProcessor,
        file_store: FileStore,
        native_service: NativeExtractionService,
        *,
        worker_count: int = 1,
        max_pages_per_session: int = 500,
    ) -> None:
        if worker_count != 1:
            raise ValueError("Phase 3 requires exactly one processing worker.")
        self._registry = registry
        self._queue = job_queue
        self._processor = processor
        self._file_store = file_store
        self._native = native_service
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
                await self._run_native(session, job, document)
            except JobCancelledError:
                await self._finalize_cancelled(session, job, document)
            except NativeExtractionError as exc:
                logger.exception(
                    "Native extraction failed",
                    extra={
                        "document_id": document.document_id,
                        "job_id": job.job_id,
                        "error_code": exc.code.value,
                        "exception_type": type(exc).__name__,
                        "failing_component": exc.failing_component
                        or type(self._native).__qualname__,
                        "operation": exc.operation or "extract_document",
                        "worker_exit_code": exc.worker_exit_code,
                        "processor_class": type(self._processor).__qualname__,
                        "native_service_class": type(self._native).__qualname__,
                    },
                )
                await self._finalize_native_failed(session, job, document, code=exc.code.value)
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
                    session, job, document, code=ErrorCode.NATIVE_EXTRACTION_FAILED.value
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
    ) -> None:
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
        document.progress_percent = _MAX_PROGRESS_PERCENT
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
            percent=_MAX_PROGRESS_PERCENT,
            document_status=DocumentStatus.NATIVE_TRUST_COMPLETE,
            pages_completed=pages_total,
            pages_total=pages_total,
            message=document.user_status_message,
        )

    async def _finalize_native_failed(
        self,
        session: RuntimeSession,
        job: ProcessingJob,
        document: RuntimeDocument,
        *,
        code: str,
    ) -> None:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(UTC)
        job.failure_code = code
        job.failure_message = "Native extraction could not be completed."
        document.status = DocumentStatus.FAILED
        document.native_extraction_performed = False
        document.native_result_available = False
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
