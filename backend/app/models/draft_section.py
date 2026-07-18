"""DraftSection entity."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import DraftSectionType, StatementSupportLabel


class DraftParagraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    supporting_fact_ids: list[str] = Field(default_factory=list)
    contains_argument: bool = False
    verification_required: bool = False
    support_label: StatementSupportLabel | None = None

    @field_validator("id")
    @classmethod
    def _para_prefix(cls, value: str) -> str:
        if not value.startswith("para_"):
            raise ValueError("id must start with para_")
        return value


class DraftSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    draft_id: str
    section_type: DraftSectionType
    heading: str
    order_index: int = Field(ge=0)
    paragraphs: list[DraftParagraph] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _sec_prefix(cls, value: str) -> str:
        if not value.startswith("sec_"):
            raise ValueError("id must start with sec_")
        return value

    @field_validator("draft_id")
    @classmethod
    def _draft_prefix(cls, value: str) -> str:
        if not value.startswith("draft_"):
            raise ValueError("draft_id must start with draft_")
        return value
