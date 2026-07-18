"""SourceToken entity."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ExtractionMethod
from app.models.geometry import NormalizedPolygon


class SourceToken(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document_id: str
    page_number: int = Field(ge=1)
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    polygon: NormalizedPolygon
    method: ExtractionMethod

    @field_validator("id")
    @classmethod
    def _tok_prefix(cls, value: str) -> str:
        if not value.startswith("tok_"):
            raise ValueError("id must start with tok_")
        return value

    @field_validator("document_id")
    @classmethod
    def _doc_prefix(cls, value: str) -> str:
        if not value.startswith("doc_"):
            raise ValueError("document_id must start with doc_")
        return value
