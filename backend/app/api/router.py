"""Top-level API router aggregation.

Health routes are mounted at the application root (no prefix), matching the
canonical contract. The versioned router is mounted under the configured API
prefix and is empty in Phase 0.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.v1.endpoints import health as health_endpoints
from backend.app.api.v1.router import router as v1_router


def build_api_router(api_prefix: str) -> APIRouter:
    """Assemble the application router for the given API prefix."""

    root = APIRouter()
    root.include_router(health_endpoints.router)
    root.include_router(v1_router, prefix=api_prefix)
    return root
