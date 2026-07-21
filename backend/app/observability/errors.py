"""Global exception handlers producing the canonical error envelope.

Clients never receive stack traces, exception strings, or filesystem paths.
The server-side exception is logged with the request id for correlation.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.contracts.errors import ApiErrorDetail, ApiErrorEnvelope, ErrorCode
from backend.app.observability.request_id import get_request_id

logger = logging.getLogger("veridemand.errors")


class ApiException(Exception):
    """Raised by domain/service code to produce the canonical error envelope.

    Carries a stable client-facing ``ErrorCode``, an HTTP status, a safe message,
    and optional non-sensitive context. Never place local paths, parser output,
    file content, or stack traces in ``message`` or ``details``.
    """

    def __init__(
        self,
        *,
        status_code: int,
        code: ErrorCode,
        message: str,
        document_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.document_id = document_id
        self.details = details or {}


_STATUS_TO_CODE: dict[int, ErrorCode] = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    422: ErrorCode.VALIDATION_ERROR,
    503: ErrorCode.SERVICE_NOT_READY,
}

_STATUS_TO_MESSAGE: dict[int, str] = {
    404: "The requested resource was not found.",
    405: "The requested method is not allowed for this resource.",
    503: "The service is not ready.",
}


def _envelope(
    *,
    code: str,
    message: str,
    request_id: str,
    status_code: int,
    document_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    envelope = ApiErrorEnvelope(
        error=ApiErrorDetail(
            code=code,
            message=message,
            request_id=request_id,
            document_id=document_id,
            details=details or {},
        )
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    """Register the canonical exception handlers on the application."""

    @app.exception_handler(ApiException)
    async def _handle_api_exception(request: Request, exc: ApiException) -> JSONResponse:
        request_id = get_request_id(request)
        return _envelope(
            code=exc.code.value,
            message=exc.message,
            request_id=request_id,
            status_code=exc.status_code,
            document_id=exc.document_id,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = get_request_id(request)
        safe_errors = [
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": error.get("msg"),
                "type": error.get("type"),
            }
            for error in exc.errors()
        ]
        return _envelope(
            code=ErrorCode.VALIDATION_ERROR.value,
            message="Request validation failed.",
            request_id=request_id,
            status_code=422,
            details={"errors": safe_errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = get_request_id(request)
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        message = _STATUS_TO_MESSAGE.get(exc.status_code)
        if message is None:
            message = (
                "An unexpected error occurred."
                if exc.status_code >= 500
                else "The request could not be completed."
            )
        return _envelope(
            code=code.value,
            message=message,
            request_id=request_id,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        logger.exception(
            "Unhandled exception (%s) for request %s",
            type(exc).__name__,
            request_id,
        )
        return _envelope(
            code=ErrorCode.INTERNAL_ERROR.value,
            message="An unexpected error occurred.",
            request_id=request_id,
            status_code=500,
        )
