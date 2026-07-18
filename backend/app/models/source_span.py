"""SourceSpan entity."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import ExtractionMethod
from app.models.geometry import NormalizedPolygon, validate_normalized_polygon


class SourceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    document_id: str
    page_number: int = Field(ge=1)
    text: str
    token_ids: list[str] = Field(default_factory=list)
    polygons: list[NormalizedPolygon]
    context: str | None = None
    method: ExtractionMethod
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("id")
    @classmethod
    def _span_prefix(cls, value: str) -> str:
        if not value.startswith("span_"):
            raise ValueError("id must start with span_")
        return value

    @field_validator("document_id")
    @classmethod
    def _doc_prefix(cls, value: str) -> str:
        if not value.startswith("doc_"):
            raise ValueError("document_id must start with doc_")
        return value

    @model_validator(mode="after")
    def _manual_requires_polygon(self) -> "SourceSpan":
        if not self.polygons:
            raise ValueError("polygons must contain at least one polygon")
        for poly in self.polygons:
            validate_normalized_polygon([(p[0], p[1]) for p in poly])
        return self
