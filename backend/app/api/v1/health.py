"""API v1 health routes: liveness and readiness."""

from fastapi import APIRouter, Request

from app.models.health import HealthResponse
from app.services.health import HealthService

router = APIRouter(prefix="/health", tags=["health"])


def _service(request: Request) -> HealthService:
    return request.app.state.health_service  # type: ignore[no-any-return]


@router.get("/live", response_model=HealthResponse)
def get_live(request: Request) -> HealthResponse:
    return _service(request).liveness()


@router.get("/ready", response_model=HealthResponse)
def get_ready(request: Request) -> HealthResponse:
    return _service(request).readiness()
