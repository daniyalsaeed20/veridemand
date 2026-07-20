"""Select classification decision from Stage A archetype + Stage B rule scores."""

from __future__ import annotations

from app.models.enums import ClassificationStatus, DocumentClassification, SafetyArchetype
from app.services.classification.archetype import ArchetypeAssessment
from app.services.classification.precedence import apply_precedence
from app.services.classification.rules_config import AMBIGUITY_SCORE_GAP, FILENAME_ONLY_CAP
from app.services.classification.types import (
    ClassificationDecision,
    ClassificationFeatures,
    ClassificationMethod,
    RuleScore,
)

_EVIDENCE_TYPES = frozenset(
    {
        DocumentClassification.POLICE_REPORT,
        DocumentClassification.INSURER_CORRESPONDENCE,
        DocumentClassification.MEDICAL_RECORD,
        DocumentClassification.IMAGING_REPORT,
        DocumentClassification.BILL_LEDGER,
        DocumentClassification.LIEN,
        DocumentClassification.WAGE_LOSS,
        DocumentClassification.PHOTOGRAPHS,
    }
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
    archetype: ArchetypeAssessment | None = None,
) -> ClassificationDecision | None:
    conflicts: list[str] = []
    arch = archetype or ArchetypeAssessment(
        archetype=SafetyArchetype.NONE,
        matched_families=(),
        evidence_marker_count=0,
        reason="none",
    )

    if not scores:
        if features.image_like:
            return ClassificationDecision(
                classification=DocumentClassification.PHOTOGRAPHS,
                confidence=0.40,
                reason="rules: image file type; limited text",
                method=ClassificationMethod.RULES,
                needs_correction=True,
                ambiguous=True,
                classification_status=ClassificationStatus.NEEDS_CONFIRMATION,
                safety_archetype=arch.archetype,
                conflicts=("limited_usable_text",),
            )
        return ClassificationDecision(
            classification=DocumentClassification.OTHER,
            confidence=0.25,
            reason="rules: no matching signals",
            method=ClassificationMethod.RULES,
            needs_correction=True,
            ambiguous=True,
            classification_status=ClassificationStatus.NEEDS_CONFIRMATION,
            safety_archetype=arch.archetype,
            conflicts=("limited_usable_text",),
        )

    ordered = apply_precedence(scores)
    top = ordered[0]
    second = ordered[1] if len(ordered) > 1 else None

    content_matches = [m for m in top.matches if m.source != "filename"]
    filename_only = not content_matches and bool(top.matches)
    confidence = top.score
    if filename_only:
        confidence = min(confidence, FILENAME_ONLY_CAP)
        conflicts.append("weak_single_signal")

    ambiguous = False
    if second is not None:
        gap = top.score - second.score
        if gap < AMBIGUITY_SCORE_GAP:
            ambiguous = True
            conflicts.append("close_scores")
        if content_matches and second.score >= threshold:
            fn_class = (
                second.classification
                if all(m.source == "filename" for m in second.matches)
                else None
            )
            if fn_class and fn_class != top.classification:
                ambiguous = True
                conflicts.append("filename_content_mismatch")

    if not features.has_usable_text and not filename_only:
        confidence = min(confidence, 0.40)
        ambiguous = True
        conflicts.append("limited_usable_text")

    # Weak: only one content match total
    if content_matches and len(content_matches) == 1 and top.score < 0.9:
        conflicts.append("weak_single_signal")
        if top.score < threshold + 0.15:
            ambiguous = True

    classification = top.classification
    reason = f"rules: {_format_reason(scores, top)}"
    safety = arch.archetype

    # Stage B demand/template content wins ⇒ mirror into safety (authority) layer
    if safety == SafetyArchetype.NONE and not filename_only:
        if classification == DocumentClassification.EXISTING_DEMAND and content_matches:
            safety = SafetyArchetype.EXISTING_DEMAND
            conflicts.append("category_implies_safety")
        elif classification == DocumentClassification.TEMPLATE and content_matches:
            safety = SafetyArchetype.TEMPLATE
            conflicts.append("category_implies_safety")

    # Stage A overrides category when demand/template structure is material
    if safety == SafetyArchetype.TEMPLATE:
        if classification != DocumentClassification.TEMPLATE:
            conflicts.append("archetype_vs_category")
            ambiguous = True
        classification = DocumentClassification.TEMPLATE
        reason = f"archetype:template; {reason}"
    elif safety == SafetyArchetype.EXISTING_DEMAND:
        if classification in _EVIDENCE_TYPES or classification == DocumentClassification.OTHER:
            conflicts.append("archetype_vs_category")
            ambiguous = True
        classification = DocumentClassification.EXISTING_DEMAND
        reason = f"archetype:existing_demand; {reason}"
    elif safety == SafetyArchetype.UNCERTAIN_DERIVATIVE:
        conflicts.append("derivative_summary_risk")
        ambiguous = True
        reason = f"archetype:uncertain_derivative; {reason}"

    # Safety-restricted documents always need confirmation even at high rule score
    if safety != SafetyArchetype.NONE:
        needs_correction = True
        if confidence >= threshold and not ambiguous:
            ambiguous = True
            if (
                "archetype_vs_category" not in conflicts
                and "category_implies_safety" not in conflicts
            ):
                conflicts.append("safety_review_required")
            elif "category_implies_safety" in conflicts and not ambiguous:
                ambiguous = True
    else:
        needs_correction = confidence < threshold or ambiguous

    if ambiguous or needs_correction:
        status = (
            ClassificationStatus.AMBIGUOUS if ambiguous else ClassificationStatus.NEEDS_CONFIRMATION
        )
    else:
        status = ClassificationStatus.PROPOSED

    # Deduplicate conflicts preserving order
    seen: set[str] = set()
    uniq_conflicts: list[str] = []
    for c in conflicts:
        if c not in seen:
            seen.add(c)
            uniq_conflicts.append(c)

    candidates = tuple((s.classification, s.score) for s in ordered[:3])
    return ClassificationDecision(
        classification=classification,
        confidence=round(confidence, 3),
        reason=reason,
        method=ClassificationMethod.RULES,
        needs_correction=needs_correction,
        candidates=candidates,
        ambiguous=ambiguous,
        classification_status=status,
        safety_archetype=safety,
        conflicts=tuple(uniq_conflicts),
    )
