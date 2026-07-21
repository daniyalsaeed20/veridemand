"""Closed enums for the document-extraction foundation shell."""

from enum import StrEnum


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"
