"""DocumentPage entity."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ExtractionMethod, PageRoute


class DocumentPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document_id: str
    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    text_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    route: PageRoute
    ocr_status: str | None = None
    extraction_method: ExtractionMethod | None = None
    quality_flags: list[str] = Field(default_factory=list)
    token_count: int | None = Field(default=None, ge=0)
    span_count: int | None = Field(default=None, ge=0)

    @field_validator("document_id")
    @classmethod
    def _doc_prefix(cls, value: str) -> str:
        if not value.startswith("doc_"):
            raise ValueError("document_id must start with doc_")
        return value
