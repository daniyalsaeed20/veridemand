"""Fact entity."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import FactStatus
from app.models.taxonomies import FACT_TYPES


class UserOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
    reason: str
    at: datetime


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    fact_type: str
    raw_value: str
    normalized_value: str | float | int | None = None
    display_value: str | None = None
    description: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    status: FactStatus
    source_span_ids: list[str] = Field(default_factory=list)
    extraction_methods: list[str] = Field(default_factory=list)
    document_ids: list[str] | None = None
    label_context: str | None = None
    criticality: Literal["critical", "normal"] | None = None
    user_override: UserOverride | None = None
    provenance: Literal["deterministic", "calculated", "user", "llm_optional"] | None = (
        "deterministic"
    )

    @field_validator("id")
    @classmethod
    def _fact_prefix(cls, value: str) -> str:
        if not value.startswith("fact_"):
            raise ValueError("id must start with fact_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value

    @field_validator("fact_type")
    @classmethod
    def _known_or_additive(cls, value: str) -> str:
        # Additive catalog: known values are preferred; unknown values are allowed
        # only if dotted form (category.specific) to avoid inventing bare codes silently.
        if value in FACT_TYPES:
            return value
        if "." in value and all(part for part in value.split(".")):
            return value
        raise ValueError("fact_type must be a dotted catalog value")
