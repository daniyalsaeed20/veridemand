"""API v1 health route."""

from fastapi import APIRouter, Request

from app.models.health import HealthResponse
from app.services.health import HealthService

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(request: Request) -> HealthResponse:
    service: HealthService = request.app.state.health_service
    return service.get_health()
