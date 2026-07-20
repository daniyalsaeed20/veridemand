"""Ephemeral types for deterministic fact extraction (not contracted entities)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentClassification, FactStatus
from app.models.fact import Fact
from app.models.issue import Issue


@dataclass(frozen=True)
class ParserHit:
    """Raw parser output before Fact persistence."""

    fact_type: str
    raw_value: str
    normalized_value: str | None
    display_value: str | None
    source_span_ids: tuple[str, ...]
    document_id: str
    page_number: int
    label_context: str | None
    parser_id: str
    extraction_methods: tuple[str, ...]
    confidence: float
    criticality: Literal["critical", "normal"]
    warnings: tuple[str, ...] = ()
    secondary_source: bool = False
    classification_ambiguous: bool = False
    page_quality_weak: bool = False


@dataclass
class FactExtractionResult:
    facts: list[Fact] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    spans_inspected: int = 0
    documents_parsed: int = 0
    documents_suppressed_authority: int = 0
    documents_suppressed_quality: int = 0
    parse_ms: float = 0.0
    llm_calls: int = 0


class FactPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: FactStatus | None = None
    value: str | None = None
    reason: str | None = None
    lock: bool | None = None


class FactListResponse(BaseModel):
    """Grouped facts for GET /facts."""

    model_config = ConfigDict(extra="forbid")

    facts: list[Fact]
    groups: dict[str, list[str]] = Field(default_factory=dict)
    counts_by_status: dict[str, int] = Field(default_factory=dict)


@dataclass(frozen=True)
class ParserSpec:
    parser_id: str
    fact_type: str
    label_cues: tuple[str, ...]
    doc_classes: frozenset[DocumentClassification]
    criticality: Literal["critical", "normal"]
    value_kind: str  # date|time|identifier|money|cpt|icd10|name|phone|email|pronoun|text
    negative_cues: tuple[str, ...] = ()
    prefer_same_line: bool = True


CRITICAL_FACT_TYPES: frozenset[str] = frozenset(
    {
        "client.name",
        "client.dob",
        "insured.name",
        "insurer.name",
        "claim.number",
        "policy.number",
        "collision.date",
        "collision.location",
        "collision.report_number",
        "medical.diagnosis",
        "damages.specials_claimed",
        "correspondence.offer_deadline",
        "client.pronouns",
    }
)

CONFLICT_ISSUE_BY_FACT_TYPE: dict[str, str] = {
    "client.name": "identity.name_conflict",
    "client.dob": "identity.dob_conflict",
    "client.pronouns": "identity.pronoun_conflict",
    "client.address": "identity.address_conflict",
    "claim.number": "claim.claim_number_conflict",
    "policy.number": "claim.policy_number_conflict",
    "insurer.name": "claim.insurer_conflict",
    "collision.date": "collision.date_of_loss_conflict",
    "collision.location": "collision.location_conflict",
    "medical.diagnosis": "medical.diagnosis_conflict",
}


def category_for_fact_type(fact_type: str) -> str:
    if "." not in fact_type:
        return "other"
    return fact_type.split(".", 1)[0]


def safe_meta(hit: ParserHit) -> dict[str, Any]:
    return {
        "parser_id": hit.parser_id,
        "secondary_source": hit.secondary_source,
        "classification_ambiguous": hit.classification_ambiguous,
        "page_quality_weak": hit.page_quality_weak,
        "warnings": list(hit.warnings),
    }
