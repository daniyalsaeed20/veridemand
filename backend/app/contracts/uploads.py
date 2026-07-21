"""Bulk upload response contracts.

A batch is processed per-file: valid files are accepted even when siblings are
rejected. Rejections never leak server paths, parser exceptions, stack traces,
or document content.
"""

from __future__ import annotations

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.documents import DocumentSummary
from backend.app.contracts.sessions import SessionSnapshot


class RejectedDocument(ApiModel):
    """A single rejected file in a bulk upload batch."""

    input_index: int = Field(ge=0, description="Original 0-based position in the multipart batch.")
    display_filename: str | None = Field(
        default=None, description="Sanitised display filename where recoverable."
    )
    error_code: str = Field(description="Stable rejection error code.")
    message: str = Field(description="Safe, non-sensitive rejection message.")
    client_media_type: str | None = Field(
        default=None, description="Client-supplied media type, echoed only when safe."
    )
    detected_format: str | None = Field(
        default=None, description="Server-detected format where safely determined."
    )


class UploadBatchResponse(ApiModel):
    """Response body for a bulk upload request (201, incl. partial acceptance)."""

    session: SessionSnapshot = Field(description="Updated session snapshot.")
    accepted: list[DocumentSummary] = Field(description="Accepted documents, in input order.")
    rejected: list[RejectedDocument] = Field(description="Rejected files, in input order.")
