"""FastAPI application factory."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1 import api_v1_router
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestIdMiddleware
from app.core.server_settings import ServerSettings, get_server_settings
from app.models.app_settings import AppSettings, ConfigurationError
from app.services.classification import ClassificationService
from app.services.documents import DocumentService
from app.services.health import HealthService
from app.services.ocr import configure_init_cooldown_ms, shutdown_adapter
from app.services.process import ProcessService
from app.services.session import SessionService

logger = get_logger(__name__)


def create_app(
    *,
    app_settings: AppSettings | None = None,
    server_settings: ServerSettings | None = None,
) -> FastAPI:
    server = server_settings or get_server_settings()
    configure_logging(server.log_level)

    try:
        settings = app_settings or AppSettings.from_environment()
    except ConfigurationError:
        logger.error("Configuration failed at startup")
        raise

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        session_service = SessionService(
            app_settings=settings,
            temp_root=server.temp_root,
            max_active_sessions=server.max_active_sessions,
        )
        document_service = DocumentService(
            session_service=session_service,
            app_settings=settings,
        )
        classification_service = ClassificationService(
            session_service=session_service,
            app_settings=settings,
        )
        process_service = ProcessService(
            session_service=session_service,
            app_settings=settings,
            server_settings=server,
            classification_service=classification_service,
        )
        session_service.set_process_drain(process_service.wait_until_idle)
        app.state.app_settings = settings
        app.state.server_settings = server
        app.state.session_service = session_service
        app.state.document_service = document_service
        app.state.classification_service = classification_service
        app.state.process_service = process_service
        app.state.health_service = HealthService(
            settings=settings,
            app_version=server.app_version or __version__,
        )
        configure_init_cooldown_ms(float(settings.ocr_init_retry_cooldown_ms))

        stop_event = asyncio.Event()

        async def sweeper() -> None:
            interval = server.session_cleanup_interval_seconds
            while not stop_event.is_set():
                try:
                    cleaned = session_service.cleanup_expired_sessions(datetime.now(UTC))
                    if cleaned:
                        logger.info(
                            "TTL sweeper cleaned sessions",
                            extra={"extra_fields": {"count": len(cleaned)}},
                        )
                except Exception:  # noqa: BLE001
                    logger.exception("TTL sweeper error")
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except TimeoutError:
                    continue

        sweeper_task = asyncio.create_task(sweeper())
        logger.info(
            "Application started",
            extra={"extra_fields": {"app_version": server.app_version}},
        )
        try:
            yield
        finally:
            stop_event.set()
            sweeper_task.cancel()
            try:
                await sweeper_task
            except asyncio.CancelledError:
                pass
            # Final cleanup of any remaining sessions
            for sid in list(getattr(session_service, "_registry", {})):
                try:
                    session_service.delete_session(sid)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Shutdown session cleanup failed",
                        extra={"extra_fields": {"session_id": sid}},
                    )
            try:
                shutdown_adapter()
            except Exception:  # noqa: BLE001
                logger.exception("OCR adapter shutdown failed")

    app = FastAPI(
        title="VeriDemand API",
        version=server.app_version,
        lifespan=lifespan,
    )
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
    app.include_router(api_v1_router)
    return app


app = create_app()
