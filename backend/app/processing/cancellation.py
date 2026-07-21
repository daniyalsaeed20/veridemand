"""Cooperative cancellation primitive for queue-admission work."""

from __future__ import annotations


class JobCancelledError(Exception):
    """Raised by admission code when it observes a cancellation request."""


class CancellationToken:
    """A simple, cooperative cancellation flag.

    Admission code checks ``cancelled`` (or calls ``raise_if_cancelled``) at safe
    points and exits promptly when cancellation has been requested. This is not a
    forced interrupt: work must cooperate.
    """

    __slots__ = ("_cancelled",)

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise JobCancelledError
