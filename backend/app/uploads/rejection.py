"""Per-file rejection signal used across the upload validation pipeline.

Validators raise ``UploadRejected`` for a single bad file; the upload service
catches it and produces a ``RejectedDocument`` without leaking paths, parser
output, archive entry content, or document text. Endpoint-level failures (session
not found, etc.) use ``ApiException`` instead.
"""

from __future__ import annotations

from backend.app.contracts.errors import ErrorCode


class UploadRejected(Exception):
    """A single uploaded file failed validation."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        detected_format: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.detected_format = detected_format
