"""Canonical API error contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from backend.app.contracts.base import ApiModel


class ErrorCode(StrEnum):
    """Stable, client-facing error codes used across the API."""

    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    VALIDATION_ERROR = "validation_error"
    CONFIGURATION_ERROR = "configuration_error"
    SERVICE_NOT_READY = "service_not_ready"
    INTERNAL_ERROR = "internal_error"


class ApiErrorDetail(ApiModel):
    """Structured, non-sensitive description of a single API error."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable, non-sensitive error message.")
    request_id: str = Field(description="Correlates the error with server logs.")
    document_id: str | None = Field(
        default=None, description="Related document identifier when applicable."
    )
    page_number: int | None = Field(
        default=None, gt=0, description="Related 1-based page number when applicable."
    )
    details: dict[str, Any] = Field(
        default_factory=dict, description="Optional structured, non-sensitive context."
    )


class ApiErrorEnvelope(ApiModel):
    """Top-level wrapper returned for every error response."""

    error: ApiErrorDetail = Field(description="The error payload.")
