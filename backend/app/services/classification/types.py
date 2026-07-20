"""Module-local classification types (not wire entities)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentClassification, DocumentFileType


class ClassificationMethod(StrEnum):
    RULES = "rules"
    LLM = "llm"
    USER_SELECTED = "user_selected"
    USER_CONFIRMED = "user_confirmed"


class AuthorityMode(StrEnum):
    AUTHORITATIVE = "authoritative"
    SECONDARY_DISABLED = "secondary_disabled"
    SECONDARY_ENABLED = "secondary_enabled"


@dataclass(frozen=True)
class ClassificationFeatures:
    document_id: str
    display_name: str
    file_type: DocumentFileType
    page_count: int
    filename_tokens: tuple[str, ...]
    extension: str
    early_page_text: str
    early_page_headings: tuple[str, ...]
    has_usable_text: bool
    usable_page_count: int
    total_early_pages: int
    image_like: bool


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    label: str
    weight: float
    source: str


@dataclass(frozen=True)
class RuleScore:
    classification: DocumentClassification
    score: float
    matches: tuple[RuleMatch, ...]


@dataclass(frozen=True)
class ClassificationDecision:
    classification: DocumentClassification
    confidence: float
    reason: str
    method: ClassificationMethod
    needs_correction: bool
    candidates: tuple[tuple[DocumentClassification, float], ...] = ()
    ambiguous: bool = False


class DocumentPresentationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: DocumentClassification | None = None
    display_name: str | None = Field(default=None, min_length=1)
    sequence_index: int | None = Field(default=None, ge=0)
    exclude_from_drafting: bool | None = None
    treat_as_secondary_evidence: bool | None = None
    confirm_classification: bool = False
    revert_to_proposed: bool = False


class DocumentSequenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[str] = Field(min_length=1)


@dataclass
class SequenceProposal:
    document_id: str
    sequence_index: int
