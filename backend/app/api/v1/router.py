"""Versioned API router mounted under the configured API prefix (e.g. /api/v1).

Intentionally empty in Phase 0. Later phases register their routes here
(sessions, uploads, processing, extraction, search, exports). No Phase 1+
endpoints exist yet.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()
