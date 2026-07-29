"""Document upload, listing, cancellation and removal endpoints."""

from __future__ import annotations

import contextlib
from typing import Annotated, Any

from fastapi import APIRouter, File, Response, UploadFile, status

from backend.app.api.v1.dependencies import (
    CoordinatorDep,
    RegistryDep,
    SchedulerDep,
    SettingsDep,
    UploadServiceDep,
)
from backend.app.contracts.documents import DocumentListResponse, DocumentSummary
from backend.app.contracts.errors import ApiErrorEnvelope, ErrorCode
from backend.app.contracts.progress import ProgressEventType
from backend.app.contracts.scheduling import (
    PriorityChangeRequest,
    PriorityChangeResponse,
    SchedulerSnapshot,
)
from backend.app.contracts.uploads import UploadBatchResponse
from backend.app.observability.errors import ApiException
from backend.app.sessions.service import build_session_snapshot

router = APIRouter(tags=["documents"])

_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorEnvelope, "description": "Session or document not found."}
}

_PRIORITY_ACTIONS = frozenset({"move_ahead", "move_behind", "restore_default_priority"})


@router.post(
    "/sessions/{session_id}/documents",
    status_code=status.HTTP_201_CREATED,
    response_model=UploadBatchResponse,
    summary="Upload one or more documents",
    responses=_NOT_FOUND_RESPONSES,
)
async def upload_documents(
    session_id: str,
    registry: RegistryDep,
    upload_service: UploadServiceDep,
    settings: SettingsDep,
    scheduler: SchedulerDep,
    files: Annotated[list[UploadFile], File(description="One or more files to upload.")],
) -> UploadBatchResponse:
    if not files:
        raise ApiException(
            status_code=400,
            code=ErrorCode.UPLOAD_NO_FILES,
            message="No files were provided.",
        )
    session = await registry.get(session_id)
    accepted, rejected = await upload_service.process_batch(session, files)
    return UploadBatchResponse(
        session=build_session_snapshot(session, settings, scheduler=scheduler),
        accepted=accepted,
        rejected=rejected,
    )


@router.get(
    "/sessions/{session_id}/documents",
    response_model=DocumentListResponse,
    summary="List a session's documents",
    responses=_NOT_FOUND_RESPONSES,
)
async def list_documents(
    session_id: str,
    registry: RegistryDep,
    settings: SettingsDep,
    scheduler: SchedulerDep,
) -> DocumentListResponse:
    session = await registry.get(session_id, touch=False)
    snapshot = build_session_snapshot(session, settings, scheduler=scheduler)
    return DocumentListResponse(documents=snapshot.documents)


@router.get(
    "/sessions/{session_id}/documents/{document_id}",
    response_model=DocumentSummary,
    summary="Get a single document",
    responses=_NOT_FOUND_RESPONSES,
)
async def get_document(
    session_id: str,
    document_id: str,
    registry: RegistryDep,
    settings: SettingsDep,
    scheduler: SchedulerDep,
) -> DocumentSummary:
    session = await registry.get(session_id, touch=False)
    snapshot = build_session_snapshot(session, settings, scheduler=scheduler)
    for document in snapshot.documents:
        if document.document_id == document_id:
            return document
    raise ApiException(
        status_code=404,
        code=ErrorCode.DOCUMENT_NOT_FOUND,
        message="Document not found in this session.",
        document_id=document_id,
    )


@router.post(
    "/sessions/{session_id}/documents/{document_id}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentSummary,
    summary="Cancel a queued or in-progress document",
    responses=_NOT_FOUND_RESPONSES,
)
async def cancel_document(
    session_id: str,
    document_id: str,
    registry: RegistryDep,
    coordinator: CoordinatorDep,
    settings: SettingsDep,
) -> DocumentSummary:
    session = await registry.get(session_id)
    document = await coordinator.cancel_document(session, document_id)
    return document.to_summary(session_id=session.session_id, api_prefix=settings.api_prefix)


@router.delete(
    "/sessions/{session_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a document and its files",
    responses=_NOT_FOUND_RESPONSES,
)
async def remove_document(
    session_id: str,
    document_id: str,
    registry: RegistryDep,
    coordinator: CoordinatorDep,
) -> Response:
    session = await registry.get(session_id)
    await coordinator.remove_document(session, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/sessions/{session_id}/documents/{document_id}/priority",
    response_model=PriorityChangeResponse,
    summary="Change a document's scheduling priority",
    responses=_NOT_FOUND_RESPONSES,
)
async def change_document_priority(
    session_id: str,
    document_id: str,
    body: PriorityChangeRequest,
    registry: RegistryDep,
    coordinator: CoordinatorDep,
    scheduler: SchedulerDep,
) -> PriorityChangeResponse:
    session = await registry.get(session_id)
    if body.action not in _PRIORITY_ACTIONS:
        raise ApiException(
            status_code=400,
            code=ErrorCode.VALIDATION_ERROR,
            message=(
                "Unsupported priority action. "
                "Expected move_ahead, move_behind, or restore_default_priority."
            ),
            document_id=document_id,
        )

    before = scheduler.get_document(document_id)
    old_class = before.priority_class if before is not None else None
    old_effective = before.effective_priority if before is not None else None

    if body.action == "move_ahead":
        success = coordinator.move_document_ahead(session_id, document_id)
    elif body.action == "move_behind":
        success = coordinator.move_document_behind(session_id, document_id)
    else:
        success = coordinator.restore_document_priority(session_id, document_id)

    after = scheduler.get_document(document_id)
    if success:
        message = f"Document priority action '{body.action}' applied."
        with contextlib.suppress(Exception):
            await session.broker.publish(
                ProgressEventType.SCHEDULER_PRIORITY_CHANGED,
                document_id=document_id,
                scheduler_priority_class=(
                    after.priority_class.value if after is not None else None
                ),
                scheduler_effective_priority=(
                    after.effective_priority if after is not None else None
                ),
                scheduler_document_state=after.state.value if after is not None else None,
                scheduler_reason=body.action,
                fair_scheduling_enabled=scheduler.enabled,
            )
    else:
        message = f"Document priority action '{body.action}' could not be applied."
    return PriorityChangeResponse(
        document_id=document_id,
        action=body.action,
        success=success,
        message=message,
        old_priority_class=old_class,
        new_priority_class=after.priority_class if after is not None else None,
        old_effective_priority=old_effective,
        new_effective_priority=after.effective_priority if after is not None else None,
        effective_next_turn=scheduler.turn_number if success else None,
    )


@router.get(
    "/sessions/{session_id}/scheduler",
    response_model=SchedulerSnapshot,
    summary="Get the fair-scheduler snapshot for a session",
    responses=_NOT_FOUND_RESPONSES,
)
async def get_scheduler_snapshot(
    session_id: str,
    registry: RegistryDep,
    scheduler: SchedulerDep,
) -> SchedulerSnapshot:
    await registry.get(session_id, touch=False)
    snap = scheduler.snapshot()
    return SchedulerSnapshot(
        scheduler_enabled=bool(snap.get("scheduler_enabled", False)),
        scheduler_policy_version=str(snap.get("scheduler_policy_version", "")),
        active_document_id=snap.get("active_document_id"),
        active_work_unit_id=snap.get("active_work_unit_id"),
        ready_document_count=int(snap.get("ready_document_count", 0) or 0),
        checkpointed_document_count=int(snap.get("checkpointed_document_count", 0) or 0),
        turn_number=int(snap.get("turn_number", 0) or 0),
        documents=[],
        estimated_batch_remaining_seconds=None,
    )
