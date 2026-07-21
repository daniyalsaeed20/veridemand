"""Builds public session read models from mutable runtime state.

Queue positions are read from the (continuously recalculated) job records so the
snapshot always reflects current ordering, never a stale stored value. Local
filesystem paths are never included.
"""

from __future__ import annotations

import time

from backend.app.contracts.jobs import JobStatus
from backend.app.contracts.sessions import (
    RUNTIME_WARNING,
    QueueInfo,
    SessionLimits,
    SessionSnapshot,
)
from backend.app.sessions.models import RuntimeSession
from backend.app.settings.config import Settings
from backend.app.uploads.formats import SUPPORTED_EXTENSIONS

# Bounded number of recent events embedded in a session snapshot.
RECENT_EVENTS_LIMIT = 50


def build_session_limits(settings: Settings) -> SessionLimits:
    return SessionLimits(
        max_files_per_session=settings.max_files_per_session,
        max_pages_per_session=settings.max_pages_per_session,
        max_single_file_bytes=settings.max_single_file_bytes,
        max_session_bytes=settings.max_session_bytes,
        max_filename_length=settings.max_filename_length,
        supported_extensions=list(SUPPORTED_EXTENSIONS),
    )


def build_session_snapshot(session: RuntimeSession, settings: Settings) -> SessionSnapshot:
    now_monotonic = time.monotonic()

    queue_positions = {
        job.document_id: job.queue_position
        for job in session.jobs.values()
        if job.status is JobStatus.QUEUED and job.queue_position is not None
    }
    documents = [
        doc.to_summary(queue_positions.get(doc.document_id)) for doc in session.documents.values()
    ]
    jobs = [job.to_summary() for job in session.jobs.values()]

    running = [job for job in session.jobs.values() if job.status is JobStatus.RUNNING]
    active = running[0] if running else None
    queue = QueueInfo(
        pending=sum(1 for job in session.jobs.values() if job.status is JobStatus.QUEUED),
        running=len(running),
        active_document_id=active.document_id if active else None,
        active_job_id=active.job_id if active else None,
    )

    return SessionSnapshot(
        session_id=session.session_id,
        status=session.status,
        created_at=session.created_at,
        last_activity_at=session.last_activity_at,
        expires_at=session.expires_at,
        expiring=session.in_warning_window(
            now_monotonic, settings.session_expiring_warning_seconds
        ),
        seconds_remaining=session.seconds_remaining(now_monotonic),
        limits=build_session_limits(settings),
        runtime_warning=RUNTIME_WARNING,
        counts=session.status_counts(),
        accepted_bytes=session.accepted_bytes,
        known_pages=session.known_pages,
        unknown_page_documents=session.unknown_page_documents(),
        queue=queue,
        documents=documents,
        jobs=jobs,
        recent_events=session.broker.recent_events(RECENT_EVENTS_LIMIT),
    )
