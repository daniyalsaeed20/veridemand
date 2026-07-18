"""PreflightFinding / PreflightReport entities."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import FindingSeverity, StatementSupportLabel


class DraftRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paragraph_id: str
    sentence_index: int | None = None


class PreflightFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    code: str
    severity: FindingSeverity
    blocking: bool
    message: str = Field(min_length=1)
    draft_ref: DraftRef | None = None
    fact_ids: list[str] | None = None
    source_span_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] | None = None
    semantic_label: StatementSupportLabel | None = None
    issue_id: str | None = None

    @field_validator("id")
    @classmethod
    def _find_prefix(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("find_"):
            raise ValueError("id must start with find_")
        return value

    @field_validator("issue_id")
    @classmethod
    def _issue_prefix(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("issue_"):
            raise ValueError("issue_id must start with issue_")
        return value


class PreflightReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    draft_id: str
    programmatic_gate: Literal["pass", "blocked"]
    findings: list[PreflightFinding] = Field(default_factory=list)
    created_at: datetime
    semantic_ran: bool | None = None
    semantic_error: str | None = None

    @field_validator("id")
    @classmethod
    def _preflight_prefix(cls, value: str) -> str:
        if not value.startswith("preflight_"):
            raise ValueError("id must start with preflight_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value

    @field_validator("draft_id")
    @classmethod
    def _draft_prefix(cls, value: str) -> str:
        if not value.startswith("draft_"):
            raise ValueError("draft_id must start with draft_")
        return value
