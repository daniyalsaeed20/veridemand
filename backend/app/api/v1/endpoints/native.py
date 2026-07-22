"""Native extraction API endpoints (Phase 3 intermediate contracts)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.api.v1.dependencies import RegistryDep, SettingsDep
from backend.app.contracts.documents import DocumentStatus
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.native import NativeDocumentSummary, NativePageResult
from backend.app.extraction.native.service import NativeExtractionService
from backend.app.observability.errors import ApiException
from backend.app.sessions.models import RuntimeDocument, RuntimeSession

router = APIRouter(tags=["native"])


def _native_service(settings: SettingsDep) -> NativeExtractionService:
    return NativeExtractionService(settings)


NativeServiceDep = Annotated[NativeExtractionService, Depends(_native_service)]


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
    "/sessions/{session_id}/documents/{document_id}/native/summary",
    response_model=NativeDocumentSummary,
)
async def get_native_summary(
    session_id: str,
    document_id: str,
    registry: RegistryDep,
    native: NativeServiceDep,
) -> NativeDocumentSummary:
    session, document = await _require_document(registry, session_id, document_id)
    if document.status in (
        DocumentStatus.UPLOADED,
        DocumentStatus.QUEUED,
        DocumentStatus.CANONICALISING,
        DocumentStatus.READY_FOR_EXTRACTION,
        DocumentStatus.INSPECTING_NATIVE,
        DocumentStatus.EXTRACTING_NATIVE,
    ):
        raise ApiException(
            status_code=409,
            code=ErrorCode.NATIVE_RESULT_NOT_READY,
            message="Native extraction results are not ready yet.",
            document_id=document_id,
        )
    summary = native.load_summary(session.session_id, document_id)
    if summary is None:
        raise ApiException(
            status_code=404,
            code=ErrorCode.NATIVE_RESULT_NOT_FOUND,
            message="Native extraction results were not found.",
            document_id=document_id,
        )
    return summary


@router.get(
    "/sessions/{session_id}/documents/{document_id}/native/pages/{page_number}",
    response_model=NativePageResult,
)
async def get_native_page(
    session_id: str,
    document_id: str,
    page_number: int,
    registry: RegistryDep,
    native: NativeServiceDep,
    include_characters: Annotated[bool, Query()] = False,
) -> NativePageResult:
    if page_number < 1:
        raise ApiException(
            status_code=404,
            code=ErrorCode.NATIVE_PAGE_NOT_FOUND,
            message="Native page was not found.",
            document_id=document_id,
            details={"page_number": page_number},
        )
    session, document = await _require_document(registry, session_id, document_id)
    if document.status in (
        DocumentStatus.UPLOADED,
        DocumentStatus.QUEUED,
        DocumentStatus.CANONICALISING,
        DocumentStatus.READY_FOR_EXTRACTION,
        DocumentStatus.INSPECTING_NATIVE,
        DocumentStatus.EXTRACTING_NATIVE,
    ):
        raise ApiException(
            status_code=409,
            code=ErrorCode.NATIVE_RESULT_NOT_READY,
            message="Native extraction results are not ready yet.",
            document_id=document_id,
        )
    if document.canonical_page_count is not None and page_number > document.canonical_page_count:
        raise ApiException(
            status_code=404,
            code=ErrorCode.NATIVE_PAGE_NOT_FOUND,
            message="Native page was not found.",
            document_id=document_id,
            details={"page_number": page_number},
        )
    page = native.load_page(session.session_id, document_id, page_number)
    if page is None:
        raise ApiException(
            status_code=404,
            code=ErrorCode.NATIVE_PAGE_NOT_FOUND,
            message="Native page was not found.",
            document_id=document_id,
            details={"page_number": page_number},
        )
    if not include_characters:
        return page.model_copy(update={"characters": []})
    if page.decision.value != "accepted":
        return page.model_copy(
            update={"characters": [], "words": [], "provisional_native_text": None}
        )
    return page
