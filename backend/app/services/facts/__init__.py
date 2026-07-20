"""Deterministic fact extraction (Phase 5)."""

from app.services.facts.service import FactService
from app.services.facts.types import FactExtractionResult, FactListResponse, FactPatch

__all__ = [
    "FactService",
    "FactExtractionResult",
    "FactListResponse",
    "FactPatch",
]
