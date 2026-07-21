"""Standard API error envelope."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.taxonomies import ErrorCode


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: ErrorCode | str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
