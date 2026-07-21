"""Canonical Pydantic contracts (machine SoT) for the document-extraction shell."""

from app.models.error_envelope import ErrorEnvelope
from app.models.health import HealthResponse

__all__ = [
    "ErrorEnvelope",
    "HealthResponse",
]
