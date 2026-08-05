"""Session lifecycle and SSE endpoints."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request, Response, status
from sse_starlette.sse import EventSourceResponse

from backend.app.api.v1.dependencies import (
    CoordinatorDep,
    RegistryDep,
    SchedulerDep,
    SettingsDep,
)
from backend.app.contracts.errors import ApiErrorEnvelope, ErrorCode
from backend.app.contracts.processing import ProcessRequest, ProcessResponse
from backend.app.contracts.sessions import SessionSnapshot
from backend.app.observability.errors import ApiException
from backend.app.progress.models import BrokerClosedError
from backend.app.progress.service import sse_event_stream
from backend.app.sessions.registry import SessionDeletionReason
from backend.app.sessions.service import build_session_snapshot

router = APIRouter(tags=["sessions"])

_SSE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Accel-Buffering": "no",
}

_SESSION_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorEnvelope, "description": "Session not found or expired."}
}


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=SessionSnapshot,
    summary="Create a runtime session",
)
async def create_session(
    registry: RegistryDep,
    settings: SettingsDep,
    scheduler: SchedulerDep,
) -> SessionSnapshot:
    session = await registry.create()
    return build_session_snapshot(session, settings, scheduler=scheduler)


@router.get(
    "/sessions/{session_id}",
    response_model=SessionSnapshot,
    summary="Get a session snapshot",
    responses=_SESSION_NOT_FOUND_RESPONSES,
)
async def get_session(
    session_id: str,
    registry: RegistryDep,
    settings: SettingsDep,
    scheduler: SchedulerDep,
) -> SessionSnapshot:
    # Reading a snapshot is not user activity: the frontend polls it on every
    # server-sent event (including the expiry warning), so touching here would
    # continually reset the inactivity TTL and a watched session could never
    # expire. Only user-initiated mutations extend the deadline.
    session = await registry.get(session_id, touch=False)
    return build_session_snapshot(session, settings, scheduler=scheduler)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a session and its data",
    responses=_SESSION_NOT_FOUND_RESPONSES,
)
async def delete_session(
    session_id: str,
    registry: RegistryDep,
) -> Response:
    await registry.delete(session_id, SessionDeletionReason.USER_DELETED)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/process",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ProcessResponse,
    summary="Queue documents for admission",
    responses=_SESSION_NOT_FOUND_RESPONSES,
)
async def process_documents(
    session_id: str,
    payload: ProcessRequest,
    registry: RegistryDep,
    coordinator: CoordinatorDep,
    settings: SettingsDep,
    scheduler: SchedulerDep,
    request: Request,
) -> ProcessResponse:
    session = await registry.get(session_id)
    if settings.ocr_enabled:
        worker = getattr(request.app.state, "ocr_worker_manager", None)
        ready = bool(worker is not None and getattr(worker, "ready", False))
        if not ready:
            message = "Printed OCR is not ready."
            if worker is not None and hasattr(worker, "runtime_status"):
                status_obj = worker.runtime_status()
                if getattr(status_obj, "user_message", None):
                    message = str(status_obj.user_message)
            raise ApiException(
                status_code=503,
                code=ErrorCode.OCR_WORKER_NOT_READY,
                message=message,
            )
    queued, ignored = await coordinator.enqueue_documents(session, payload.document_ids)
    return ProcessResponse(
        queued=queued,
        ignored=ignored,
        session=build_session_snapshot(session, settings, scheduler=scheduler),
    )


@router.get(
    "/sessions/{session_id}/events",
    summary="Subscribe to live session progress (SSE)",
    responses=_SESSION_NOT_FOUND_RESPONSES,
)
async def session_events(
    session_id: str,
    request: Request,
    registry: RegistryDep,
    settings: SettingsDep,
) -> EventSourceResponse:
    # A reconnecting EventSource must not extend the TTL, so do not touch here.
    session = await registry.get(session_id, touch=False)
    broker = session.broker

    if broker.subscriber_count >= settings.max_sse_connections_per_session:
        raise ApiException(
            status_code=429,
            code=ErrorCode.SSE_CONNECTION_LIMIT,
            message="Too many live connections for this session.",
        )

    last_event_id = request.headers.get("last-event-id")
    try:
        connect = await broker.connect(last_event_id)
    except BrokerClosedError:
        raise ApiException(
            status_code=404,
            code=ErrorCode.SESSION_NOT_FOUND,
            message="Session not found.",
        ) from None

    async def _guarded_stream() -> AsyncIterator[dict[str, str]]:
        try:
            async for message in sse_event_stream(broker, connect):
                yield message
        finally:
            await broker.disconnect(connect.subscriber)

    return EventSourceResponse(
        _guarded_stream(),
        ping=settings.sse_heartbeat_seconds,
        headers=_SSE_HEADERS,
    )
