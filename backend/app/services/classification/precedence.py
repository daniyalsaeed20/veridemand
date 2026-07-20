"""Deterministic precedence for overlapping classification signals."""

from __future__ import annotations

from app.models.enums import DocumentClassification
from app.services.classification.rules_config import PRECEDENCE_TIERS
from app.services.classification.types import RuleScore


def tier_rank(classification: DocumentClassification) -> int:
    for idx, tier in enumerate(PRECEDENCE_TIERS):
        if classification in tier:
            return idx
    return len(PRECEDENCE_TIERS)


def apply_precedence(scores: list[RuleScore]) -> list[RuleScore]:
    """Sort scores by score desc, then precedence tier, then enum value."""
    return sorted(
        scores,
        key=lambda s: (-s.score, tier_rank(s.classification), s.classification.value),
    )
