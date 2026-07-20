"""Document entity."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    ClassificationStatus,
    DocumentClassification,
    DocumentFileType,
    DocumentStatus,
    SafetyArchetype,
)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    display_name: str = Field(min_length=1)
    file_type: DocumentFileType
    content_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-fA-F]{64}$")
    page_count: int | None = Field(default=None, ge=0)
    classification: DocumentClassification | None = None
    classification_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    classification_reason: str | None = None
    classification_status: ClassificationStatus | None = None
    safety_archetype: SafetyArchetype | None = None
    classification_conflicts: list[str] = Field(default_factory=list)
    sequence_index: int | None = Field(default=None, ge=0)
    status: DocumentStatus
    exclude_from_drafting: bool = False
    treat_as_secondary_evidence: bool = False
    page_quality_warning_count: int | None = Field(default=None, ge=0)
    error_code: str | None = None
    error_message: str | None = None

    @field_validator("id")
    @classmethod
    def _doc_prefix(cls, value: str) -> str:
        if not value.startswith("doc_"):
            raise ValueError("id must start with doc_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value
