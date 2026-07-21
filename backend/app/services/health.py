"""HealthService — liveness and readiness payloads for the foundation shell."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.enums import HealthStatus
from app.models.health import HealthResponse
from app.models.taxonomies import CONTRACTS_VERSION


class HealthService:
    def __init__(self, app_version: str) -> None:
        self._app_version = app_version

    def _response(self, message: str | None = None) -> HealthResponse:
        return HealthResponse(
            status=HealthStatus.OK,
            api_version="v1",
            app_version=self._app_version,
            contracts_version=CONTRACTS_VERSION,
            time_utc=datetime.now(UTC),
            message=message,
        )

    def liveness(self) -> HealthResponse:
        return self._response()

    def readiness(self) -> HealthResponse:
        return self._response()
