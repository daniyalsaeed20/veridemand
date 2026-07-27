"""Routing package errors (privacy-safe)."""

from __future__ import annotations


class PageRoutingError(Exception):
    """Raised when page routing cannot complete safely."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)
