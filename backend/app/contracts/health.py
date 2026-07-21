"""Health and readiness contracts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field

from backend.app.contracts.base import ApiModel


class HealthState(StrEnum):
    """Overall health/readiness states."""

    OK = "ok"
    READY = "ready"
    DEGRADED = "degraded"
    NOT_READY = "not_ready"


class CheckState(StrEnum):
    """Result of a single readiness dependency check."""

    PASS = "pass"
    FAIL = "fail"
    NOT_CONFIGURED = "not_configured"


class DependencyCheck(ApiModel):
    """Outcome of one readiness dependency check."""

    name: str = Field(description="Stable identifier of the checked dependency.")
    status: CheckState = Field(description="Result of the check.")
    required: bool = Field(description="Whether this check must pass for readiness.")
    message: str | None = Field(
        default=None, description="Optional non-sensitive detail about the check."
    )


class LivenessResponse(ApiModel):
    """Response for the liveness probe."""

    status: Literal["ok"] = Field(default="ok", description="Always 'ok' when the process runs.")
    service: Literal["veridemand-api"] = Field(
        default="veridemand-api", description="Service identifier."
    )
    app_name: str = Field(description="Configured application name.")
    version: str = Field(description="Application version.")
    timestamp: datetime = Field(description="Timezone-aware UTC time of the response.")
    request_id: str = Field(description="Correlates the response with server logs.")


class ReadinessResponse(ApiModel):
    """Response for the readiness probe."""

    status: Literal["ready", "degraded", "not_ready"] = Field(
        description="Aggregate readiness state derived from the checks."
    )
    service: Literal["veridemand-api"] = Field(
        default="veridemand-api", description="Service identifier."
    )
    app_name: str = Field(description="Configured application name.")
    version: str = Field(description="Application version.")
    timestamp: datetime = Field(description="Timezone-aware UTC time of the response.")
    request_id: str = Field(description="Correlates the response with server logs.")
    checks: list[DependencyCheck] = Field(description="Individual dependency check results.")
