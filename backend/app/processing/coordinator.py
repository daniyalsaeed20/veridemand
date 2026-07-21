"""Processing coordinator: a single admission worker over the in-memory queue.

Owns the queue worker task, job state transitions, cancellation, session-state
updates, event publication, and graceful shutdown. FastAPI ``BackgroundTasks``
is deliberately not used for the queue. Phase 1 runs exactly one worker; multiple
workers are forbidden by configuration.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from backend.app.contracts.documents import DocumentStatus
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.identifiers import new_job_id
from backend.app.contracts.jobs import JobStatus, JobSummary
from backend.app.contracts.processing import IgnoredDocument
from backend.app.contracts.progress import ProgressEventType
from backend.app.observability.errors import ApiException
from backend.app.processing.admission import AdmissionProcessor
from backend.app.processing.cancellation import JobCancelledError
from backend.app.processing.models import ProcessingJob
from backend.app.processing.queue import JobQueue, QueueClosedError
from backend.app.progress.broker import EventBroker
from backend.app.progress.models import BrokerClosedError
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.sessions.registry import SessionRegistry
from backend.app.sessions.service import recompute_session_status

logger = logging.getLogger("veridemand.processing")

_ADMISSION_FAILURE_CODE = "admission_failed"
_DOCUMENT_STAGE = "preparing"
_MAX_PROGRESS_PERCENT = 5


async def _safe_publish(broker: EventBroker, event: ProgressEventType, **fields: object) -> None:
    with contextlib.suppress(BrokerClosedError):
        await broker.publish(event, **fields)  # type: ignore[arg-type]


class ProcessingCoordinator:
    """Coordinates queue admission with a single cooperative worker."""

    def __init__(
        self,
        registry: SessionRegistry,
        job_queue: JobQueue,
        admission: AdmissionProcessor,
        *,
        worker_count: int = 1,
    ) -> None:
        if worker_count != 1:
            raise ValueError("Phase 1 requires exactly one admission worker.")
        self._registry = registry
        self._queue = job_queue
        self._admission = admission
        self._worker: asyncio.Task[None] | None = None
        self._current_job: ProcessingJob | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running and self._worker is not None and not self._worker.done()

    def start(self) -> None:
        if self._worker is not None:
            return
        self._running = True
        self._worker = asyncio.create_task(self._worker_loop(), name="admission-worker")

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
        """Cancel a queued/preparing document (see Section 27 semantics)."""

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
                return document  # idempotent

            if document.status in (
                DocumentStatus.UPLOADED,
                DocumentStatus.READY_FOR_EXTRACTION,
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
            elif document.status is DocumentStatus.PREPARING and job is not None:
                # Cooperative: the worker observes the token and finalises.
                job.request_cancellation()

            recompute_session_status(session)
            return document

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            self._current_job = job
            try:
                await self._run_job(job)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error running admission job.")
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
        document.status = DocumentStatus.PREPARING
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
            percent=_MAX_PROGRESS_PERCENT,
            document_status=DocumentStatus.PREPARING,
        )

        try:
            await self._admission.prepare(session, document, job.cancellation)
        except JobCancelledError:
            await self._finalize_cancelled(session, job, document)
        except Exception as exc:  # translate any admission failure into a safe state
            logger.warning("Admission failed for a document: %s", type(exc).__name__)
            await self._finalize_failed(session, job, document)
        else:
            job.status = JobStatus.COMPLETED
            job.finished_at = datetime.now(UTC)
            document.status = DocumentStatus.READY_FOR_EXTRACTION
            await _safe_publish(
                session.broker,
                ProgressEventType.DOCUMENT_READY_FOR_EXTRACTION,
                document_id=document.document_id,
                job_id=job.job_id,
                percent=_MAX_PROGRESS_PERCENT,
                document_status=DocumentStatus.READY_FOR_EXTRACTION,
            )
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

    @staticmethod
    def _finalize_orphan(job: ProcessingJob) -> None:
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)

    async def _finalize_cancelled(
        self, session: RuntimeSession, job: ProcessingJob, document: RuntimeDocument
    ) -> None:
        job.status = JobStatus.CANCELLED
        job.finished_at = datetime.now(UTC)
        document.status = DocumentStatus.CANCELLED
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
        self, session: RuntimeSession, job: ProcessingJob, document: RuntimeDocument
    ) -> None:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(UTC)
        job.failure_code = _ADMISSION_FAILURE_CODE
        job.failure_message = "Queue admission could not be completed."
        document.status = DocumentStatus.FAILED
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
