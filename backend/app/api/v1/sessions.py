"""Session, document, and Phase 3 process/viewer API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response

from app.models.case_session import CaseSession
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.document_upload_batch import DocumentUploadBatch
from app.models.issue import Issue
from app.models.process_event import ProcessEvent
from app.models.source_span import SourceSpan
from app.models.source_token import SourceToken
from app.services.classification import ClassificationService
from app.services.classification.types import DocumentPresentationPatch, DocumentSequenceUpdate
from app.services.documents import DocumentService
from app.services.process import ProcessService
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


@router.patch(
    "/sessions/{session_id}/documents/{document_id}",
    response_model=Document,
)
def patch_document(
    session_id: str,
    document_id: str,
    patch: DocumentPresentationPatch,
    request: Request,
) -> Document:
    service: ClassificationService = request.app.state.classification_service
    return service.update_document_presentation(session_id, document_id, patch)


@router.put(
    "/sessions/{session_id}/documents/sequence",
    response_model=list[Document],
)
def update_document_sequence(
    session_id: str,
    body: DocumentSequenceUpdate,
    request: Request,
) -> list[Document]:
    service: ClassificationService = request.app.state.classification_service
    return service.update_document_sequence(session_id, body)


@router.post("/sessions/{session_id}/process", response_model=list[ProcessEvent])
def start_process(session_id: str, request: Request) -> list[ProcessEvent]:
    """Start background processing; poll GET .../events for completion."""
    service: ProcessService = request.app.state.process_service
    return service.start_process(session_id)


@router.get("/sessions/{session_id}/events", response_model=list[ProcessEvent])
def list_events(
    session_id: str,
    request: Request,
    after: Annotated[int, Query(ge=-1)] = -1,
) -> list[ProcessEvent]:
    service: ProcessService = request.app.state.process_service
    return service.list_events(session_id, after=after)


@router.get("/sessions/{session_id}/issues", response_model=list[Issue])
def list_issues(session_id: str, request: Request) -> list[Issue]:
    service: ProcessService = request.app.state.process_service
    return service.list_issues(session_id)


@router.get(
    "/sessions/{session_id}/documents/{document_id}/pages",
    response_model=list[DocumentPage],
)
def list_pages(session_id: str, document_id: str, request: Request) -> list[DocumentPage]:
    service: ProcessService = request.app.state.process_service
    return service.list_pages(session_id, document_id)


@router.get(
    "/sessions/{session_id}/documents/{document_id}/pages/{page_number}",
    response_model=DocumentPage,
)
def get_page(session_id: str, document_id: str, page_number: int, request: Request) -> DocumentPage:
    service: ProcessService = request.app.state.process_service
    return service.get_page(session_id, document_id, page_number)


@router.post(
    "/sessions/{session_id}/documents/{document_id}/pages/{page_number}/ocr/retry",
    response_model=DocumentPage,
)
def retry_ocr_page(
    session_id: str, document_id: str, page_number: int, request: Request
) -> DocumentPage:
    service: ProcessService = request.app.state.process_service
    return service.retry_ocr_page(session_id, document_id, page_number)


@router.get("/sessions/{session_id}/documents/{document_id}/view")
def get_canonical_view(session_id: str, document_id: str, request: Request) -> FileResponse:
    service: ProcessService = request.app.state.process_service
    path = service.get_canonical_pdf_path(session_id, document_id)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"{document_id}.pdf",
        content_disposition_type="inline",
    )


@router.get("/sessions/{session_id}/documents/{document_id}/thumbnails/{page_number}")
def get_thumbnail(
    session_id: str, document_id: str, page_number: int, request: Request
) -> FileResponse:
    service: ProcessService = request.app.state.process_service
    path = service.get_thumbnail_path(session_id, document_id, page_number)
    return FileResponse(path, media_type="image/png", filename=f"page_{page_number}.png")


@router.get(
    "/sessions/{session_id}/documents/{document_id}/pages/{page_number}/tokens",
    response_model=list[SourceToken],
)
def list_tokens(
    session_id: str, document_id: str, page_number: int, request: Request
) -> list[SourceToken]:
    service: ProcessService = request.app.state.process_service
    return service.list_tokens(session_id, document_id, page_number)


@router.get(
    "/sessions/{session_id}/documents/{document_id}/pages/{page_number}/spans",
    response_model=list[SourceSpan],
)
def list_spans(
    session_id: str, document_id: str, page_number: int, request: Request
) -> list[SourceSpan]:
    service: ProcessService = request.app.state.process_service
    return service.list_spans(session_id, document_id, page_number)
