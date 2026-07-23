"""Canonical PDF delivery, metadata and synthetic overlay endpoints (Phase 2)."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse

from backend.app.api.v1.dependencies import FileStoreDep, RegistryDep, SettingsDep
from backend.app.contracts.canonical import (
    CanonicalDocumentMetadata,
    CanonicalStatus,
    OverlayProofItem,
    OverlayProofResponse,
)
from backend.app.contracts.errors import ApiErrorEnvelope, ErrorCode
from backend.app.contracts.geometry import phase2_alignment_geometry
from backend.app.observability.errors import ApiException
from backend.app.sessions.models import RuntimeDocument, RuntimeSession

router = APIRouter(tags=["canonical"])
logger = logging.getLogger("veridemand.canonical.api")

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ApiErrorEnvelope, "description": "Session or document not found."},
    409: {"model": ApiErrorEnvelope, "description": "Canonical document not ready."},
}


def _require_document(session: RuntimeSession, document_id: str) -> RuntimeDocument:
    document = session.documents.get(document_id)
    if document is None:
        raise ApiException(
            status_code=404,
            code=ErrorCode.DOCUMENT_NOT_FOUND,
            message="Document not found in this session.",
            document_id=document_id,
        )
    return document


def _require_ready(document: RuntimeDocument) -> None:
    if (
        document.canonical_status is not CanonicalStatus.READY
        or not document.canonical_view_available
    ):
        raise ApiException(
            status_code=409,
            code=ErrorCode.CANONICAL_DOCUMENT_NOT_READY,
            message="Canonical document is not ready.",
            document_id=document.document_id,
        )


def _safe_pdf_filename(display_filename: str) -> str:
    stem = display_filename.rsplit(".", 1)[0] if "." in display_filename else display_filename
    cleaned = (
        "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in stem).strip() or "document"
    )
    return f"{cleaned}.pdf"


@router.get(
    "/sessions/{session_id}/documents/{document_id}/canonical",
    summary="Download or stream the canonical PDF",
    responses=_ERROR_RESPONSES,
)
async def get_canonical_pdf(
    session_id: str,
    document_id: str,
    request: Request,
    registry: RegistryDep,
    file_store: FileStoreDep,
    settings: SettingsDep,
) -> Response:
    started = time.perf_counter()
    range_header = request.headers.get("range")
    range_start: int | None = None
    range_end: int | None = None
    if range_header and range_header.lower().startswith("bytes="):
        spec = range_header[6:].strip()
        if "-" in spec:
            start_s, _, end_s = spec.partition("-")
            try:
                range_start = int(start_s) if start_s else None
            except ValueError:
                range_start = None
            try:
                range_end = int(end_s) if end_s else None
            except ValueError:
                range_end = None

    session = await registry.get(session_id, touch=False)
    document = _require_document(session, document_id)
    _require_ready(document)

    path = file_store.canonical_path(session_id, document_id)
    if not path.is_file():
        from backend.app.contracts.documents import DocumentStatus

        document.canonical_status = CanonicalStatus.FAILED
        document.canonical_view_available = False
        document.canonical_failure_code = ErrorCode.CANONICAL_DOCUMENT_NOT_FOUND.value
        document.status = DocumentStatus.FAILED
        duration_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "canonical_request",
            extra={
                "document_id": document_id,
                "response_status": 404,
                "range_requested": range_header is not None,
                "range_start": range_start,
                "range_end": range_end,
                "content_length": None,
                "content_type": None,
                "duration_ms": duration_ms,
            },
        )
        raise ApiException(
            status_code=404,
            code=ErrorCode.CANONICAL_DOCUMENT_NOT_FOUND,
            message="Canonical document file is missing.",
            document_id=document_id,
        )

    filename = _safe_pdf_filename(document.display_filename)
    content_length = path.stat().st_size
    headers = {
        "Cache-Control": settings.canonical_file_cache_control,
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}",
    }
    duration_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "canonical_request",
        extra={
            "document_id": document_id,
            "response_status": 206 if range_header else 200,
            "range_requested": range_header is not None,
            "range_start": range_start,
            "range_end": range_end,
            "content_length": content_length,
            "content_type": "application/pdf",
            "duration_ms": duration_ms,
        },
    )
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        headers=headers,
        content_disposition_type="inline",
    )


@router.get(
    "/sessions/{session_id}/documents/{document_id}/canonical/metadata",
    response_model=CanonicalDocumentMetadata,
    summary="Canonical page metadata",
    responses=_ERROR_RESPONSES,
)
async def get_canonical_metadata(
    session_id: str,
    document_id: str,
    registry: RegistryDep,
) -> CanonicalDocumentMetadata:
    session = await registry.get(session_id, touch=False)
    document = _require_document(session, document_id)
    _require_ready(document)
    if (
        document.canonicalisation_method is None
        or document.canonical_sha256 is None
        or document.canonical_size_bytes is None
        or document.canonical_page_count is None
        or document.canonical_created_at is None
    ):
        raise ApiException(
            status_code=409,
            code=ErrorCode.CANONICAL_DOCUMENT_NOT_READY,
            message="Canonical metadata is incomplete.",
            document_id=document_id,
        )
    return CanonicalDocumentMetadata(
        document_id=document.document_id,
        canonical_status=document.canonical_status,
        canonicalisation_method=document.canonicalisation_method,
        media_type="application/pdf",
        size_bytes=document.canonical_size_bytes,
        sha256=document.canonical_sha256,
        page_count=document.canonical_page_count,
        pages=list(document.canonical_pages),
        created_at=document.canonical_created_at,
        libreoffice_version=document.libreoffice_version,
        warnings=list(document.canonical_warning_codes),
    )


@router.get(
    "/sessions/{session_id}/documents/{document_id}/canonical/overlay-proof",
    response_model=OverlayProofResponse,
    summary="Synthetic Phase 2 alignment overlay proof",
    responses=_ERROR_RESPONSES,
)
async def get_overlay_proof(
    session_id: str,
    document_id: str,
    registry: RegistryDep,
) -> OverlayProofResponse:
    session = await registry.get(session_id, touch=False)
    document = _require_document(session, document_id)
    _require_ready(document)
    page_count = document.canonical_page_count or 0
    if page_count < 1:
        raise ApiException(
            status_code=409,
            code=ErrorCode.CANONICAL_DOCUMENT_NOT_READY,
            message="Canonical pages are not available.",
            document_id=document_id,
        )
    geometry = phase2_alignment_geometry()
    overlays = [
        OverlayProofItem(
            id="phase2_alignment_box",
            label="Alignment test",
            source="synthetic_phase_2",
            synthetic=True,
            page_number=page_number,
            geometry=geometry,
        )
        for page_number in range(1, page_count + 1)
    ]
    return OverlayProofResponse(document_id=document.document_id, synthetic=True, overlays=overlays)
