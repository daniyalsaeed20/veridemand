"""Canonicalisation domain errors with stable client-facing codes."""

from __future__ import annotations

from backend.app.contracts.errors import ErrorCode


class CanonicalisationError(Exception):
    """Raised when canonical PDF production or inspection fails."""

    __slots__ = ("code",)

    def __init__(self, code: ErrorCode, message: str = "") -> None:
        super().__init__(message or code.value)
        self.code = code
