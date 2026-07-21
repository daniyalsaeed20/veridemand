"""FastAPI application factory for the document-extraction foundation shell."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_v1_router
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware
from app.core.server_settings import ServerSettings, get_server_settings
from app.services.health import HealthService

logger = get_logger(__name__)


def create_app(*, server_settings: ServerSettings | None = None) -> FastAPI:
    server = server_settings or get_server_settings()
    configure_logging(server.log_level)

    app = FastAPI(title="VeriDemand API", version=server.app_version)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=server.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    register_exception_handlers(app)
    app.state.health_service = HealthService(app_version=server.app_version or __version__)
    app.include_router(api_v1_router)
    logger.info(
        "Application started",
        extra={"extra_fields": {"app_version": server.app_version}},
    )
    return app


app = create_app()
