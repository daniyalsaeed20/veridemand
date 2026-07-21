"""Global exception handlers producing the standard error envelope."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import get_request_id
from app.models.error_envelope import ErrorEnvelope
from app.models.taxonomies import ErrorCode

logger = logging.getLogger(__name__)


def _envelope(
    *,
    error_code: str,
    message: str,
    request_id: str,
    status_code: int,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorEnvelope(
        error_code=error_code,
        message=message,
        details=dict(details or {}),
        request_id=request_id,
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = get_request_id(request)
        safe_details = {
            "errors": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]
        }
        return _envelope(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            request_id=request_id,
            details=safe_details,
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = get_request_id(request)
        if exc.status_code == 404:
            code: str = ErrorCode.ROUTE_NOT_FOUND
            message = "The requested API route was not found."
        else:
            code = ErrorCode.INTERNAL_ERROR
            message = (
                str(exc.detail) if isinstance(exc.detail, str) else "An unexpected error occurred."
            )
        return _envelope(
            error_code=code,
            message=message,
            request_id=request_id,
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = get_request_id(request)
        logger.exception(
            "Unhandled exception",
            extra={"extra_fields": {"request_id": request_id, "exc_type": type(exc).__name__}},
        )
        return _envelope(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred.",
            request_id=request_id,
            status_code=500,
        )
