"""HealthService — safe health payload."""

from __future__ import annotations

from datetime import UTC, datetime

from app.models.app_settings import AppSettings, get_safe_config_summary
from app.models.enums import HealthStatus
from app.models.health import HealthCapabilities, HealthResponse
from app.models.taxonomies import CONTRACTS_VERSION
from app.services.ocr import ocr_capability_enabled


class HealthService:
    def __init__(self, settings: AppSettings, app_version: str) -> None:
        self._settings = settings
        self._app_version = app_version

    def get_health(self) -> HealthResponse:
        summary = get_safe_config_summary(self._settings)
        capabilities = HealthCapabilities(
            ocr_enabled=ocr_capability_enabled(),
            llm_semantic_extraction_enabled=bool(summary["llm_semantic_extraction_enabled"]),
            max_files_per_session=int(summary["max_files_per_session"]),
            max_pages_per_session=int(summary["max_pages_per_session"]),
        )
        return HealthResponse(
            status=HealthStatus.OK,
            api_version="v1",
            app_version=self._app_version,
            contracts_version=CONTRACTS_VERSION,
            time_utc=datetime.now(UTC),
            capabilities=capabilities,
            message=None,
        )
