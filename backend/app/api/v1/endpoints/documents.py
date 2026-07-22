"""Document upload, listing, cancellation and removal endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, File, Response, UploadFile, status

from backend.app.api.v1.dependencies import (
    CoordinatorDep,
    RegistryDep,
    SettingsDep,
    UploadServiceDep,
)
from backend.app.contracts.documents import DocumentListResponse, DocumentSummary
from backend.app.contracts.errors import ApiErrorEnvelope, ErrorCode
from backend.app.contracts.uploads import UploadBatchResponse
from backend.app.observability.errors import ApiException
from backend.app.sessions.service import build_session_snapshot

router = APIRouter(tags=["documents"])

_NOT_FOUND_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorEnvelope, "description": "Session or document not found."}
}


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
        session=build_session_snapshot(session, settings),
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
) -> DocumentListResponse:
    session = await registry.get(session_id, touch=False)
    snapshot = build_session_snapshot(session, settings)
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
) -> DocumentSummary:
    session = await registry.get(session_id, touch=False)
    snapshot = build_session_snapshot(session, settings)
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
