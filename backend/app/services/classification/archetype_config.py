"""Structural demand/template archetype signal families (case-independent)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalFamily:
    family_id: str
    phrases: tuple[str, ...]
    kind: str  # demand | template | either


# Demand-letter structural families — require combinations, not isolated words.
# Do NOT include bare evidence phrases like "police report" here (those are Stage B).
DEMAND_FAMILIES: tuple[SignalFamily, ...] = (
    SignalFamily(
        "re_block",
        (
            "re: your insured",
            "re: claim",
            "re: our client",
            "our client,",
            "date of loss",
            "dol:",
            "claimant:",
        ),
        "demand",
    ),
    SignalFamily(
        "settlement_demand",
        (
            "demand for settlement",
            "settlement demand",
            "policy limits demand",
            "we hereby demand",
            "we demand",
            "demand package",
            "settlement proposal",
            "offer expires",
            "time-limited demand",
            "demand letter",
        ),
        "demand",
    ),
    SignalFamily(
        "damages_specials",
        (
            "general damages",
            "medical specials",
            "special damages",
            "pain and suffering",
            "specials total",
            "settlement amount",
        ),
        "demand",
    ),
    SignalFamily(
        "attorney_closing",
        (
            "very truly yours",
            "respectfully submitted",
            "attorney at law",
            "esq.",
            "counsel for plaintiff",
            "counsel for the claimant",
        ),
        "demand",
    ),
    SignalFamily(
        "exhibit_list",
        ("exhibit a", "exhibit list", "enclosed please find", "enclosures:", "exhibits:"),
        "demand",
    ),
    SignalFamily(
        "placeholders_flags",
        ("[settlement amount", "tbd]", "[tbd", "attorney comment", "flag:", "todo:"),
        "demand",
    ),
)

TEMPLATE_FAMILIES: tuple[SignalFamily, ...] = (
    SignalFamily(
        "merge_placeholders",
        (
            "[client name]",
            "[insert",
            "[claimant",
            "[insurer",
            "{{",
            "{%",
            "demand template",
            "sample demand",
            "template instructions",
            "firm template",
        ),
        "template",
    ),
    SignalFamily(
        "instructional",
        (
            "replace this section",
            "insert client",
            "fill in",
            "placeholder",
            "do not use as evidence",
        ),
        "template",
    ),
)

# Evidence-category phrase families used to detect multi-category summary density
EVIDENCE_SUMMARY_MARKERS: tuple[str, ...] = (
    "police report",
    "collision report",
    "medical records",
    "billing ledger",
    "cpt code",
    "claim number",
    "insurance company",
    "wage loss",
    "radiology report",
    "physical examination",
    "icd-10",
    "icd10",
    "chief complaint",
    "treatment summary",
    "progress note",
)

MIN_DEMAND_FAMILIES = 2
MIN_TEMPLATE_FAMILIES = 1
MIN_EVIDENCE_MARKERS_FOR_DERIVATIVE = 3
