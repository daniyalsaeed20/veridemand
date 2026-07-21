"""Request-ID middleware and helpers.

An inbound ``X-Request-ID`` is preserved only when it is safe and reasonably
sized; otherwise a fresh UUID-based identifier is generated. The resolved id is
stored on ``request.state`` and echoed on every response.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 128

# Printable, non-whitespace token: rejects control characters and newlines.
_VALID_REQUEST_ID = re.compile(rf"^[A-Za-z0-9._\-]{{1,{MAX_REQUEST_ID_LENGTH}}}$")


def new_request_id() -> str:
    """Generate a fresh UUID-based request id."""

    return uuid.uuid4().hex


def sanitize_request_id(candidate: str | None) -> str:
    """Return the candidate if it is a safe, bounded token, else a new id."""

    if candidate is not None and _VALID_REQUEST_ID.match(candidate):
        return candidate
    return new_request_id()


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a correlation id for every request and response."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def get_request_id(request: Request) -> str:
    """Return the request id stored in request state, or a fresh one."""

    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str):
        return request_id
    return new_request_id()
