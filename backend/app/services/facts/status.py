"""Conservative fact status assignment (never equate OCR conf with fact conf)."""

from __future__ import annotations

from app.models.enums import FactStatus
from app.services.facts.types import CRITICAL_FACT_TYPES, ParserHit


def score_and_status(hit: ParserHit) -> tuple[float, FactStatus]:
    conf = hit.confidence
    for _ in hit.warnings:
        conf = max(0.0, conf - 0.05)
    if hit.page_quality_weak:
        conf = max(0.0, conf - 0.15)
    if hit.classification_ambiguous:
        conf = max(0.0, conf - 0.1)
    if hit.secondary_source:
        conf = max(0.0, conf - 0.2)

    critical = hit.criticality == "critical" or hit.fact_type in CRITICAL_FACT_TYPES

    if hit.normalized_value is None:
        return conf, FactStatus.NEEDS_REVIEW

    if hit.secondary_source:
        return conf, FactStatus.NEEDS_REVIEW

    if hit.classification_ambiguous:
        return conf, FactStatus.NEEDS_REVIEW

    if hit.page_quality_weak and critical:
        return conf, FactStatus.NEEDS_REVIEW

    blocking_warnings = {
        "ambiguous_day_month_order",
        "invalid_date",
        "invalid_decimal",
        "ocr_confused_digits",
        "invalid_phone",
        "invalid_email",
        "invalid_cpt",
        "invalid_icd10",
        "templateish",
        "negative_cue",
        "attorney_contact_not_claimant",
        "demand_amount_not_charge",
        "footer_date",
    }
    for w in hit.warnings:
        if any(w.startswith(b) or w == b for b in blocking_warnings):
            return conf, FactStatus.NEEDS_REVIEW

    # Auto-verify only when strong support
    strong = (
        conf >= 0.9
        and len(hit.source_span_ids) >= 1
        and not hit.secondary_source
        and not hit.classification_ambiguous
        and not hit.page_quality_weak
        and hit.normalized_value is not None
    )
    if strong and not critical:
        return conf, FactStatus.VERIFIED

    # Critical: even strong single-source stays suggested / needs_review (catalog matrix)
    if critical:
        if conf >= 0.95 and len(hit.source_span_ids) >= 2 and not hit.warnings:
            return conf, FactStatus.VERIFIED
        if conf < 0.75:
            return conf, FactStatus.NEEDS_REVIEW
        return conf, FactStatus.SUGGESTED

    if conf < 0.7:
        return conf, FactStatus.NEEDS_REVIEW
    return conf, FactStatus.SUGGESTED
