"""Visual OCR API endpoints (Phase 4 intermediate contracts)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from backend.app.api.v1.dependencies import RegistryDep, SettingsDep
from backend.app.contracts.documents import DocumentStatus
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.visual import VisualDocumentSummary, VisualPageResult
from backend.app.extraction.visual.service import VisualOcrService
from backend.app.observability.errors import ApiException
from backend.app.sessions.models import RuntimeDocument, RuntimeSession

router = APIRouter(tags=["visual"])

_NOT_READY = {
    DocumentStatus.UPLOADED,
    DocumentStatus.QUEUED,
    DocumentStatus.CANONICALISING,
    DocumentStatus.READY_FOR_EXTRACTION,
    DocumentStatus.INSPECTING_NATIVE,
    DocumentStatus.EXTRACTING_NATIVE,
    DocumentStatus.NATIVE_TRUST_COMPLETE,
    DocumentStatus.VISUAL_PENDING,
    DocumentStatus.VISUAL_PROCESSING,
}


def _visual_service(request: Request, settings: SettingsDep) -> VisualOcrService:
    existing = getattr(request.app.state, "visual_service", None)
    if isinstance(existing, VisualOcrService):
        return existing
    if not settings.ocr_enabled:
        raise ApiException(
            status_code=503,
            code=ErrorCode.OCR_RUNTIME_UNAVAILABLE,
            message="Printed OCR is not enabled in this runtime.",
        )
    return VisualOcrService(settings)


VisualServiceDep = Annotated[VisualOcrService, Depends(_visual_service)]


async def _require_document(
    registry: RegistryDep, session_id: str, document_id: str
) -> tuple[RuntimeSession, RuntimeDocument]:
    session = await registry.get(session_id, touch=False)
    document = session.documents.get(document_id)
    if document is None:
        raise ApiException(
            status_code=404,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found in this session.",
            document_id=document_id,
        )
    return session, document


@router.get(
    "/sessions/{session_id}/documents/{document_id}/visual/summary",
    response_model=VisualDocumentSummary,
)
async def get_visual_summary(
    session_id: str,
    document_id: str,
    registry: RegistryDep,
    visual: VisualServiceDep,
) -> VisualDocumentSummary:
    session, document = await _require_document(registry, session_id, document_id)
    if document.status in _NOT_READY and not document.visual_processing_performed:
        raise ApiException(
            status_code=409,
            code=ErrorCode.VISUAL_RESULT_NOT_READY,
            message="Visual OCR results are not ready yet.",
            document_id=document_id,
        )
    summary = visual.load_summary(session.session_id, document_id)
    if summary is None:
        raise ApiException(
            status_code=404,
            code=ErrorCode.VISUAL_RESULT_NOT_FOUND,
            message="Visual OCR results were not found.",
            document_id=document_id,
        )
    return summary


@router.get(
    "/sessions/{session_id}/documents/{document_id}/visual/pages/{page_number}",
    response_model=VisualPageResult,
)
async def get_visual_page(
    session_id: str,
    document_id: str,
    page_number: int,
    registry: RegistryDep,
    visual: VisualServiceDep,
    include_lines: Annotated[bool, Query()] = True,
    include_words: Annotated[bool, Query()] = True,
    include_blocks: Annotated[bool, Query()] = True,
) -> VisualPageResult:
    if page_number < 1:
        raise ApiException(
            status_code=404,
            code=ErrorCode.VISUAL_PAGE_NOT_FOUND,
            message="Visual page was not found.",
            document_id=document_id,
            details={"page_number": page_number},
        )
    session, document = await _require_document(registry, session_id, document_id)
    if document.status in _NOT_READY and not document.visual_processing_performed:
        raise ApiException(
            status_code=409,
            code=ErrorCode.VISUAL_RESULT_NOT_READY,
            message="Visual OCR results are not ready yet.",
            document_id=document_id,
        )
    if document.canonical_page_count is not None and page_number > document.canonical_page_count:
        raise ApiException(
            status_code=404,
            code=ErrorCode.VISUAL_PAGE_NOT_FOUND,
            message="Visual page was not found.",
            document_id=document_id,
            details={"page_number": page_number},
        )
    page = visual.load_page(session.session_id, document_id, page_number)
    if page is None:
        raise ApiException(
            status_code=404,
            code=ErrorCode.VISUAL_PAGE_NOT_FOUND,
            message="Visual page was not found.",
            document_id=document_id,
            details={"page_number": page_number},
        )
    updates: dict[str, object] = {}
    if not include_lines:
        updates["lines"] = []
    if not include_words:
        updates["words"] = []
    if not include_blocks:
        updates["blocks"] = []
    if updates:
        return page.model_copy(update=updates)
    return page
