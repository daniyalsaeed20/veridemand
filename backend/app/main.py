"""FastAPI application factory for the VeriDemand document-extraction platform.

The factory performs no heavy work at import time: it initialises no future
extraction models, opens no network connections, and loads no OCR/vision
dependencies. The Phase 2 runtime services (session registry, in-memory queue,
canonicalisation coordinator, cleanup worker) are constructed and started inside
the application lifespan and torn down on shutdown.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import build_api_router
from backend.app.canonical.processor import DefaultCanonicalisationProcessor
from backend.app.cleanup.service import CleanupService
from backend.app.cleanup.worker import CleanupWorker
from backend.app.health.service import HealthService
from backend.app.observability.errors import register_exception_handlers
from backend.app.observability.request_id import RequestIdMiddleware
from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.processing.queue import InMemoryJobQueue
from backend.app.sessions.registry import SessionRegistry
from backend.app.settings.config import Settings, get_settings
from backend.app.storage.file_store import FileStore
from backend.app.uploads.service import UploadService

_DESCRIPTION = "Runtime-only document extraction platform API."


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and stop the Phase 2 runtime services around request serving."""

    settings: Settings = app.state.settings

    file_store = FileStore(settings.temp_root)
    job_queue = InMemoryJobQueue()
    registry = SessionRegistry(settings, file_store, job_queue)
    processor = DefaultCanonicalisationProcessor(
        settings,
        file_store,
        thread_workers=settings.canonicalisation_thread_workers,
        test_hold_seconds=settings.queue_admission_test_delay_seconds,
    )
    coordinator = ProcessingCoordinator(
        registry,
        job_queue,
        processor,
        file_store,
        worker_count=settings.canonicalisation_workers,
        max_pages_per_session=settings.max_pages_per_session,
    )
    upload_service = UploadService(settings, file_store)
    cleanup_service = CleanupService(registry, file_store, settings)
    cleanup_worker = CleanupWorker(cleanup_service, settings.session_cleanup_interval_seconds)

    cleanup_service.startup_sweep()
    coordinator.start()
    cleanup_worker.start()

    app.state.file_store = file_store
    app.state.job_queue = job_queue
    app.state.session_registry = registry
    app.state.coordinator = coordinator
    app.state.upload_service = upload_service
    app.state.cleanup_service = cleanup_service
    app.state.cleanup_worker = cleanup_worker
    health_service: HealthService = app.state.health_service
    health_service.attach_runtime(
        coordinator=coordinator, cleanup_worker=cleanup_worker, job_queue=job_queue
    )

    try:
        yield
    finally:
        await cleanup_worker.stop()
        await coordinator.stop()
        await cleanup_service.shutdown_cleanup()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""

    resolved = settings or get_settings()
    logging.basicConfig(level=resolved.log_level)

    app = FastAPI(
        title="VeriDemand API",
        version=resolved.app_version,
        description=_DESCRIPTION,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
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
