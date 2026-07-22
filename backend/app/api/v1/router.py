"""Versioned API router mounted under the configured API prefix (e.g. /api/v1).

Phase 1 registers the runtime session, document (upload/list/cancel/remove),
process and job routes plus the SSE progress stream. Extraction, search and
export routes remain for later phases.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1.endpoints import canonical as canonical_endpoints
from backend.app.api.v1.endpoints import documents as document_endpoints
from backend.app.api.v1.endpoints import jobs as job_endpoints
from backend.app.api.v1.endpoints import native as native_endpoints
from backend.app.api.v1.endpoints import sessions as session_endpoints

router = APIRouter()
router.include_router(session_endpoints.router)
router.include_router(document_endpoints.router)
router.include_router(canonical_endpoints.router)
router.include_router(native_endpoints.router)
router.include_router(job_endpoints.router)
