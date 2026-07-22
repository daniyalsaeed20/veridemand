"""Native extraction domain errors mapped to API error codes."""

from __future__ import annotations

from backend.app.contracts.errors import ErrorCode


class NativeExtractionError(Exception):
    """Raised when native extraction fails in a controlled way."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        worker_exit_code: int | None = None,
        operation: str | None = None,
        failing_component: str | None = None,
        page_number: int | None = None,
        exception_type: str | None = None,
        recoverable_as_visual_authority: bool = False,
        stderr_tail: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.worker_exit_code = worker_exit_code
        self.operation = operation
        self.failing_component = failing_component
        self.page_number = page_number
        self.exception_type = exception_type
        self.recoverable_as_visual_authority = recoverable_as_visual_authority
        self.stderr_tail = stderr_tail
        super().__init__(message)
