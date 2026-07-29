"""Shared FastAPI dependencies resolving runtime services from app state.

The runtime services are constructed and started by the application lifespan and
stored on ``app.state``; these helpers expose them to the versioned endpoints.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from backend.app.processing.coordinator import ProcessingCoordinator
from backend.app.processing.fair_scheduler import FairDocumentScheduler
from backend.app.sessions.registry import SessionRegistry
from backend.app.settings.config import Settings
from backend.app.storage.file_store import FileStore
from backend.app.uploads.service import UploadService


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_registry(request: Request) -> SessionRegistry:
    registry: SessionRegistry = request.app.state.session_registry
    return registry


def get_coordinator(request: Request) -> ProcessingCoordinator:
    coordinator: ProcessingCoordinator = request.app.state.coordinator
    return coordinator


def get_scheduler(request: Request) -> FairDocumentScheduler:
    scheduler: FairDocumentScheduler = request.app.state.scheduler
    return scheduler


def get_upload_service(request: Request) -> UploadService:
    service: UploadService = request.app.state.upload_service
    return service


def get_file_store(request: Request) -> FileStore:
    file_store: FileStore = request.app.state.file_store
    return file_store


# Annotated dependency aliases (avoid call-in-default-argument warnings).
SettingsDep = Annotated[Settings, Depends(get_settings)]
RegistryDep = Annotated[SessionRegistry, Depends(get_registry)]
CoordinatorDep = Annotated[ProcessingCoordinator, Depends(get_coordinator)]
SchedulerDep = Annotated[FairDocumentScheduler, Depends(get_scheduler)]
UploadServiceDep = Annotated[UploadService, Depends(get_upload_service)]
FileStoreDep = Annotated[FileStore, Depends(get_file_store)]
