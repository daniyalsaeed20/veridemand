"""FastAPI application factory for the VeriDemand document-extraction platform.

The factory performs no heavy work at import time: it initialises no future
models, opens no network connections, and constructs no processing services.
Only the health service (a pure settings-derived object) is created eagerly.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import build_api_router
from backend.app.health.service import HealthService
from backend.app.observability.errors import register_exception_handlers
from backend.app.observability.request_id import RequestIdMiddleware
from backend.app.settings.config import Settings, get_settings

_DESCRIPTION = "Runtime-only document extraction platform API."


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application.

    A ``Settings`` instance can be injected for tests without touching global
    process state.
    """

    resolved = settings or get_settings()
    logging.basicConfig(level=resolved.log_level)

    app = FastAPI(
        title="VeriDemand API",
        version=resolved.app_version,
        description=_DESCRIPTION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.state.settings = resolved
    app.state.health_service = HealthService(resolved)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)
    app.include_router(build_api_router(resolved.api_prefix))

    return app


app = create_app()
