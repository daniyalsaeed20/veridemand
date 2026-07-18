"""HealthResponse contract."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import HealthStatus
from app.models.taxonomies import CONTRACTS_VERSION


class HealthCapabilities(BaseModel):
    model_config = ConfigDict(extra="allow")

    ocr_enabled: bool
    llm_semantic_extraction_enabled: bool
    max_files_per_session: int
    max_pages_per_session: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HealthStatus
    api_version: str = "v1"
    app_version: str | None = None
    contracts_version: str = Field(default=CONTRACTS_VERSION)
    time_utc: datetime
    capabilities: HealthCapabilities | dict[str, Any]
    message: str | None = None
