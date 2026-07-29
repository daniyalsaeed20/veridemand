"""FastAPI application factory for the VeriDemand document-extraction platform.

The factory performs no heavy work at import time: it initialises no future
extraction models, opens no network connections, and loads no OCR/vision
dependencies. The Phase 2 runtime services (session registry, in-memory queue,
canonicalisation coordinator, cleanup worker) are constructed and started inside
the application lifespan and torn down on shutdown.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import build_api_router
from backend.app.canonical.processor import DefaultCanonicalisationProcessor
from backend.app.cleanup.service import CleanupService
from backend.app.cleanup.worker import CleanupWorker
from backend.app.extraction.native.service import NativeExtractionService
from backend.app.extraction.visual.service import VisualOcrService
from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.health.service import HealthService
from backend.app.observability.errors import register_exception_handlers
from backend.app.observability.request_id import RequestIdMiddleware
from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.processing.fair_scheduler import FairDocumentScheduler, SchedulerConfig
from backend.app.processing.queue import InMemoryJobQueue
from backend.app.sessions.registry import SessionRegistry
from backend.app.settings.config import Settings, get_settings
from backend.app.storage.file_store import FileStore
from backend.app.uploads.service import UploadService

_DESCRIPTION = "Runtime-only document extraction platform API."


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start and stop the Phase 2 runtime services around request serving."""

    import asyncio
    import os

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
    native_service = NativeExtractionService(settings)
    ocr_worker_manager = OcrWorkerManager(settings)
    visual_service = (
        VisualOcrService(settings, ocr_worker_manager) if settings.ocr_enabled else None
    )
    coordinator = ProcessingCoordinator(
        registry,
        job_queue,
        processor,
        file_store,
        native_service,
        visual_service,
        worker_count=settings.canonicalisation_workers,
        max_pages_per_session=settings.max_pages_per_session,
    )
    scheduler = FairDocumentScheduler(
        SchedulerConfig(
            enabled=settings.fair_ocr_scheduling_enabled,
            page_quantum=settings.fair_ocr_page_quantum,
            repair_page_quantum=settings.fair_repair_page_quantum,
            short_document_heavy_page_threshold=settings.short_document_heavy_page_threshold,
            aging_enabled=settings.scheduler_aging_enabled,
            aging_interval_seconds=settings.scheduler_aging_interval_seconds,
            max_consecutive_turns=settings.scheduler_max_consecutive_turns,
            policy_version=settings.scheduler_policy_version,
        )
    )
    coordinator.set_scheduler(scheduler)
    upload_service = UploadService(settings, file_store)
    cleanup_service = CleanupService(registry, file_store, settings)
    cleanup_worker = CleanupWorker(cleanup_service, settings.session_cleanup_interval_seconds)

    cleanup_service.startup_sweep()
    ocr_start_task: asyncio.Task[None] | None = None

    async def _start_ocr_background() -> None:
        try:
            logging.getLogger("veridemand").info(
                "OCR worker startup beginning",
                extra={
                    "component": "lifespan",
                    "operation": "ocr_worker_start",
                    "pid": os.getpid(),
                },
            )
            await ocr_worker_manager.start()
            logging.getLogger("veridemand").info(
                "OCR worker startup finished",
                extra={
                    "component": "lifespan",
                    "operation": "ocr_worker_ready",
                    "pid": os.getpid(),
                    **ocr_worker_manager.describe(),
                },
            )
        except Exception:
            logging.getLogger("veridemand").exception(
                "OCR worker failed to start",
                extra={"component": "lifespan", "operation": "ocr_worker_start"},
            )

    # Uvicorn --reload: lifespan runs only in the serving child, not the
    # reloader parent — so exactly one OCR worker attaches to the process that
    # accepts requests. Do not block API accept on cold Paddle load; readiness
    # stays 503 and POST /process rejects until the worker is ready.
    if settings.ocr_enabled and os.environ.get("VERIDEMAND_SKIP_OCR_WORKER") != "1":
        ocr_start_task = asyncio.create_task(_start_ocr_background(), name="ocr-worker-start")
    coordinator.start()
    cleanup_worker.start()

    app.state.file_store = file_store
    app.state.job_queue = job_queue
    app.state.session_registry = registry
    app.state.coordinator = coordinator
    app.state.scheduler = scheduler
    app.state.native_service = native_service
    app.state.visual_service = visual_service
    app.state.ocr_worker_manager = ocr_worker_manager
    app.state.upload_service = upload_service
    app.state.cleanup_service = cleanup_service
    app.state.cleanup_worker = cleanup_worker
    health_service: HealthService = app.state.health_service
    health_service.attach_runtime(
        coordinator=coordinator,
        cleanup_worker=cleanup_worker,
        job_queue=job_queue,
        ocr_worker_manager=ocr_worker_manager,
    )

    try:
        yield
    finally:
        if ocr_start_task is not None and not ocr_start_task.done():
            ocr_start_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ocr_start_task
        await cleanup_worker.stop()
        scheduler.close()
        await coordinator.stop()
        await ocr_worker_manager.stop()
        await cleanup_service.shutdown_cleanup()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application."""

    resolved = settings or get_settings()
    from backend.app.observability.dev_logging import configure_dev_logging

    configure_dev_logging(resolved.log_level)

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
        # PDF.js (cross-origin from the Vite origin) must read range headers
        # to stream canonical PDFs; omitting them causes blank pages on large files.
        expose_headers=[
            "X-Request-ID",
            "Accept-Ranges",
            "Content-Range",
            "Content-Length",
            "Content-Type",
        ],
    )

    register_exception_handlers(app)
    app.include_router(build_api_router(resolved.api_prefix))

    return app


app = create_app()
