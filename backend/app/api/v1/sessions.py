"""Session and document API routes (Phase 1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import Response

from app.models.case_session import CaseSession
from app.models.document import Document
from app.models.document_upload_batch import DocumentUploadBatch
from app.services.documents import DocumentService
from app.services.session import SessionService

router = APIRouter(tags=["sessions"])


@router.post("/sessions", response_model=CaseSession)
def create_session(request: Request) -> CaseSession:
    service: SessionService = request.app.state.session_service
    return service.create_session()


@router.get("/sessions/{session_id}", response_model=CaseSession)
def get_session(session_id: str, request: Request) -> CaseSession:
    service: SessionService = request.app.state.session_service
    return service.get_session(session_id, touch=True)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, request: Request) -> Response:
    service: SessionService = request.app.state.session_service
    service.delete_session(session_id)
    return Response(status_code=204)


@router.post("/sessions/{session_id}/documents", response_model=DocumentUploadBatch)
async def upload_documents(
    session_id: str,
    request: Request,
    files: Annotated[list[UploadFile], File()],
) -> DocumentUploadBatch:
    service: DocumentService = request.app.state.document_service
    return await service.upload_documents(session_id, files)


@router.get("/sessions/{session_id}/documents", response_model=list[Document])
def list_documents(session_id: str, request: Request) -> list[Document]:
    service: DocumentService = request.app.state.document_service
    return service.list_documents(session_id)


@router.delete("/sessions/{session_id}/documents/{document_id}", status_code=204)
def delete_document(session_id: str, document_id: str, request: Request) -> Response:
    service: DocumentService = request.app.state.document_service
    service.delete_document(session_id, document_id)
    return Response(status_code=204)
