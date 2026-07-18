"""API error envelope from docs/contracts/error-codes.md."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.taxonomies import ErrorCode


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: ErrorCode | str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    document_id: str | None = None
    request_id: str | None = None
