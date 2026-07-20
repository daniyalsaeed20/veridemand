"""Stage A — demand/template/derivative safety archetype assessment."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import DocumentFileType, SafetyArchetype
from app.services.classification.archetype_config import (
    DEMAND_FAMILIES,
    EVIDENCE_SUMMARY_MARKERS,
    MIN_DEMAND_FAMILIES,
    MIN_EVIDENCE_MARKERS_FOR_DERIVATIVE,
    MIN_TEMPLATE_FAMILIES,
    TEMPLATE_FAMILIES,
    SignalFamily,
)
from app.services.classification.types import ClassificationFeatures


@dataclass(frozen=True)
class ArchetypeAssessment:
    archetype: SafetyArchetype
    matched_families: tuple[str, ...]
    evidence_marker_count: int
    reason: str


def _family_hits(text: str, families: tuple[SignalFamily, ...]) -> list[str]:
    hits: list[str] = []
    for family in families:
        if any(phrase in text for phrase in family.phrases):
            hits.append(family.family_id)
    return hits


def assess_safety_archetype(features: ClassificationFeatures) -> ArchetypeAssessment:
    """Deterministic structural archetype; independent of Stage B taxonomy winner."""
    text = f"{features.early_page_text} {' '.join(features.early_page_headings)}".lower()
    fn = " ".join(features.filename_tokens)

    demand_hits = _family_hits(text, DEMAND_FAMILIES)
    template_hits = _family_hits(text, TEMPLATE_FAMILIES)
    evidence_markers = sum(1 for m in EVIDENCE_SUMMARY_MARKERS if m in text)

    if len(template_hits) >= MIN_TEMPLATE_FAMILIES and (
        "merge_placeholders" in template_hits or len(template_hits) >= 2
    ):
        return ArchetypeAssessment(
            archetype=SafetyArchetype.TEMPLATE,
            matched_families=tuple(template_hits),
            evidence_marker_count=evidence_markers,
            reason=f"template families: {', '.join(template_hits)}",
        )

    if len(demand_hits) >= MIN_DEMAND_FAMILIES:
        return ArchetypeAssessment(
            archetype=SafetyArchetype.EXISTING_DEMAND,
            matched_families=tuple(demand_hits),
            evidence_marker_count=evidence_markers,
            reason=f"demand families: {', '.join(demand_hits)}",
        )

    if "settlement_demand" in demand_hits and (
        "attorney_closing" in demand_hits
        or "re_block" in demand_hits
        or "damages_specials" in demand_hits
    ):
        return ArchetypeAssessment(
            archetype=SafetyArchetype.EXISTING_DEMAND,
            matched_families=tuple(demand_hits),
            evidence_marker_count=evidence_markers,
            reason=f"demand families: {', '.join(demand_hits)}",
        )

    has_settlement = "settlement_demand" in demand_hits or "re_block" in demand_hits
    if has_settlement and evidence_markers >= MIN_EVIDENCE_MARKERS_FOR_DERIVATIVE:
        return ArchetypeAssessment(
            archetype=SafetyArchetype.EXISTING_DEMAND
            if "settlement_demand" in demand_hits
            else SafetyArchetype.UNCERTAIN_DERIVATIVE,
            matched_families=tuple(demand_hits),
            evidence_marker_count=evidence_markers,
            reason="settlement/re signals with multi-category summary density",
        )

    # DOCX packages that summarize multiple evidence categories are typically
    # demand drafts/defect fixtures — never auto-primary (PDFs remain evidence).
    if (
        features.file_type == DocumentFileType.DOCX
        and evidence_markers >= 2
        and (
            bool(demand_hits)
            or "demand" in fn
            or features.page_count >= 4
            or "settlement" in text
            or evidence_markers >= MIN_EVIDENCE_MARKERS_FOR_DERIVATIVE
        )
    ):
        arch = (
            SafetyArchetype.EXISTING_DEMAND
            if ("settlement_demand" in demand_hits or "demand" in fn)
            else SafetyArchetype.UNCERTAIN_DERIVATIVE
        )
        return ArchetypeAssessment(
            archetype=arch,
            matched_families=tuple(demand_hits),
            evidence_marker_count=evidence_markers,
            reason="docx multi-category summary derivative/demand risk",
        )

    if "demand" in fn and len(demand_hits) >= 1 and evidence_markers >= 2:
        return ArchetypeAssessment(
            archetype=SafetyArchetype.UNCERTAIN_DERIVATIVE,
            matched_families=tuple(demand_hits),
            evidence_marker_count=evidence_markers,
            reason="weak demand filename with multi-evidence summary",
        )

    return ArchetypeAssessment(
        archetype=SafetyArchetype.NONE,
        matched_families=tuple(demand_hits + template_hits),
        evidence_marker_count=evidence_markers,
        reason="no material demand/template structure",
    )
