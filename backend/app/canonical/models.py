"""Internal canonicalisation result models (never exposed directly via API)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from backend.app.contracts.canonical import (
    CanonicalisationMethod,
    CanonicalPageMetadata,
)


@dataclass(frozen=True)
class CanonicalisationResult:
    """Outcome of producing and inspecting a canonical PDF."""

    pages: list[CanonicalPageMetadata]
    method: CanonicalisationMethod
    sha256: str
    size_bytes: int
    path: Path
    libreoffice_version: str | None = None
    warnings: list[str] = field(default_factory=list)
