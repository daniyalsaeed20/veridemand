"""Issue entity."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import IssueSeverity, IssueStatus
from app.models.taxonomies import ISSUE_TYPES


class IssueResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option: str
    note: str | None = None
    at: datetime
    actor: str | None = None


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    issue_type: str
    severity: IssueSeverity
    title: str = Field(min_length=1)
    explanation: str
    source_span_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] | None = None
    document_ids: list[str] | None = None
    options: list[str] | None = None
    blocking: bool
    status: IssueStatus
    resolution: IssueResolution | None = None

    @field_validator("id")
    @classmethod
    def _issue_prefix(cls, value: str) -> str:
        if not value.startswith("issue_"):
            raise ValueError("id must start with issue_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value

    @field_validator("issue_type")
    @classmethod
    def _known_or_additive(cls, value: str) -> str:
        if value in ISSUE_TYPES:
            return value
        if "." in value and all(part for part in value.split(".")):
            return value
        raise ValueError("issue_type must be a dotted catalog value")
