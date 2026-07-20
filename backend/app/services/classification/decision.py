"""Select classification decision from rule scores."""

from __future__ import annotations

from app.models.enums import DocumentClassification
from app.services.classification.precedence import apply_precedence
from app.services.classification.rules_config import AMBIGUITY_SCORE_GAP, FILENAME_ONLY_CAP
from app.services.classification.types import (
    ClassificationDecision,
    ClassificationFeatures,
    ClassificationMethod,
    RuleScore,
)


def _format_reason(scores: list[RuleScore], winner: RuleScore) -> str:
    parts: list[str] = []
    for m in winner.matches[:4]:
        parts.append(f"{m.source}: {m.label}")
    if len(winner.matches) > 4:
        parts.append(f"+{len(winner.matches) - 4} more signals")
    return "; ".join(parts) if parts else "rules: insufficient signals"


def select_rule_decision(
    features: ClassificationFeatures,
    scores: list[RuleScore],
    *,
    threshold: float,
) -> ClassificationDecision | None:
    if not scores:
        if features.image_like:
            return ClassificationDecision(
                classification=DocumentClassification.PHOTOGRAPHS,
                confidence=0.40,
                reason="rules: image file type; limited text",
                method=ClassificationMethod.RULES,
                needs_correction=True,
                ambiguous=True,
            )
        return ClassificationDecision(
            classification=DocumentClassification.OTHER,
            confidence=0.25,
            reason="rules: no matching signals",
            method=ClassificationMethod.RULES,
            needs_correction=True,
            ambiguous=True,
        )

    ordered = apply_precedence(scores)
    top = ordered[0]
    second = ordered[1] if len(ordered) > 1 else None

    content_matches = [m for m in top.matches if m.source != "filename"]
    filename_only = not content_matches and top.matches
    confidence = top.score
    if filename_only:
        confidence = min(confidence, FILENAME_ONLY_CAP)

    ambiguous = False
    if second is not None:
        gap = top.score - second.score
        if gap < AMBIGUITY_SCORE_GAP:
            ambiguous = True
        # Filename vs content disagreement
        if content_matches and second.score >= threshold:
            top_content_class = top.classification
            fn_class = (
                second.classification
                if all(m.source == "filename" for m in second.matches)
                else None
            )
            if fn_class and fn_class != top_content_class:
                ambiguous = True

    if not features.has_usable_text and not filename_only:
        confidence = min(confidence, 0.40)
        ambiguous = True

    needs_correction = confidence < threshold or ambiguous
    candidates = tuple((s.classification, s.score) for s in ordered[:3])
    reason = f"rules: {_format_reason(scores, top)}"

    return ClassificationDecision(
        classification=top.classification,
        confidence=round(confidence, 3),
        reason=reason,
        method=ClassificationMethod.RULES,
        needs_correction=needs_correction,
        candidates=candidates,
        ambiguous=ambiguous,
    )
