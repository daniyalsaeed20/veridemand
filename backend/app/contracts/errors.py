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

    # Sessions (Phase 1).
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_EXPIRED = "session_expired"
    SESSION_LIMIT_EXCEEDED = "session_limit_exceeded"
    SESSION_DELETING = "session_deleting"

    # Documents (Phase 1).
    DOCUMENT_NOT_FOUND = "document_not_found"
    DOCUMENT_PROCESSING = "document_processing"
    INVALID_DOCUMENT_STATE = "invalid_document_state"

    # Jobs / queue (Phase 1).
    JOB_NOT_FOUND = "job_not_found"
    JOB_ALREADY_TERMINAL = "job_already_terminal"
    QUEUE_CLOSED = "queue_closed"

    # Uploads (Phase 1).
    UPLOAD_NO_FILES = "upload_no_files"
    UPLOAD_EMPTY_FILE = "upload_empty_file"
    UPLOAD_INVALID_FILENAME = "upload_invalid_filename"
    UPLOAD_UNSUPPORTED_TYPE = "upload_unsupported_type"
    UPLOAD_SIGNATURE_MISMATCH = "upload_signature_mismatch"
    UPLOAD_MIME_MISMATCH = "upload_mime_mismatch"
    UPLOAD_TOO_LARGE = "upload_too_large"
    UPLOAD_ENCRYPTED_PDF = "upload_encrypted_pdf"
    UPLOAD_CORRUPT_FILE = "upload_corrupt_file"
    UPLOAD_MACROS_NOT_SUPPORTED = "upload_macros_not_supported"
    UPLOAD_ARCHIVE_UNSAFE = "upload_archive_unsafe"
    UPLOAD_ARCHIVE_TOO_LARGE = "upload_archive_too_large"
    UPLOAD_IMAGE_TOO_LARGE = "upload_image_too_large"

    # SSE (Phase 1).
    SSE_CONNECTION_LIMIT = "sse_connection_limit"
    SSE_STREAM_CLOSED = "sse_stream_closed"


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
