"""Native extraction domain errors mapped to API error codes."""

from __future__ import annotations

from backend.app.contracts.errors import ErrorCode


class NativeExtractionError(Exception):
    """Raised when native extraction fails in a controlled way."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)
