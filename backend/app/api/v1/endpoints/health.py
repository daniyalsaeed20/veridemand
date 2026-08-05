"""Health probe endpoints.

These routes are intentionally served at the application root (outside the
versioned ``/api/v1`` prefix) to match the canonical API contract. They live in
the ``v1/endpoints`` package for organisational consistency but are mounted
without a prefix by ``backend.app.api.router``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from fastapi import APIRouter, Request, Response, status

from backend.app.build_identity import build_identity_fields
from backend.app.contracts.errors import ApiErrorEnvelope
from backend.app.contracts.health import (
    HealthState,
    LivenessResponse,
    ReadinessResponse,
)
from backend.app.health.service import HealthService
from backend.app.observability.request_id import get_request_id
from backend.app.settings.config import Settings

router = APIRouter(tags=["health"])


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _health_service(request: Request) -> HealthService:
    service: HealthService = request.app.state.health_service
    return service


def _identity_kwargs(settings: Settings) -> dict[str, object]:
    identity = build_identity_fields(settings)
    app_version = str(identity["application_version"])
    process_id = identity["process_id"]
    worker_gen = identity["worker_generation"]
    assert isinstance(process_id, int)
    assert isinstance(worker_gen, int)
    return {
        "version": app_version,
        "application_version": app_version,
        "git_commit": identity["git_commit"],
        "process_id": process_id,
        "worker_generation": worker_gen,
        "configuration_profile": str(identity["configuration_profile"]),
    }


@router.get(
    "/health/live",
    operation_id="health_live",
    summary="Liveness probe",
    response_model=LivenessResponse,
)
async def health_live(request: Request) -> LivenessResponse:
    """Return 200 while the process is running. No expensive work is performed."""

    settings = _settings(request)
    identity = _identity_kwargs(settings)
    return LivenessResponse(
        app_name=settings.app_name,
        timestamp=datetime.now(UTC),
        request_id=get_request_id(request),
        version=str(identity["version"]),
        application_version=str(identity["application_version"]),
        git_commit=cast(str | None, identity["git_commit"]),
        process_id=cast(int, identity["process_id"]),
        worker_generation=cast(int, identity["worker_generation"]),
        configuration_profile=str(identity["configuration_profile"]),
    )


@router.get(
    "/health/ready",
    operation_id="health_ready",
    summary="Readiness probe",
    response_model=ReadinessResponse,
    responses={503: {"model": ApiErrorEnvelope, "description": "Service is not ready."}},
)
async def health_ready(request: Request, response: Response) -> ReadinessResponse:
    """Report readiness for Phase 0 required dependencies.

    Returns 200 when all required checks pass and 503 when any required check
    fails. Optional future dependencies never make the service unready.
    """

    settings = _settings(request)
    service = _health_service(request)
    checks = service.readiness_checks()
    state = HealthService.overall_state(checks)
    if state is HealthState.NOT_READY:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    ocr_runtime = service.ocr_runtime_status()
    if ocr_runtime is not None and ocr_runtime.retry_after_seconds is not None:
        response.headers["Retry-After"] = str(ocr_runtime.retry_after_seconds)
    identity = _identity_kwargs(settings)
    return ReadinessResponse(
        status=cast(Literal["ready", "degraded", "not_ready"], state.value),
        app_name=settings.app_name,
        timestamp=datetime.now(UTC),
        request_id=get_request_id(request),
        checks=checks,
        ocr_runtime=ocr_runtime,
        version=str(identity["version"]),
        application_version=str(identity["application_version"]),
        git_commit=cast(str | None, identity["git_commit"]),
        process_id=cast(int, identity["process_id"]),
        worker_generation=cast(int, identity["worker_generation"]),
        configuration_profile=str(identity["configuration_profile"]),
    )
