"""HealthResponse contract for the foundation shell."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import HealthStatus
from app.models.taxonomies import CONTRACTS_VERSION


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HealthStatus
    api_version: str = "v1"
    app_version: str | None = None
    contracts_version: str = Field(default=CONTRACTS_VERSION)
    time_utc: datetime
    message: str | None = None
