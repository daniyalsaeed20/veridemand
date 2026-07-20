"""Optional LLM classification fallback (disabled by default)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentClassification
from app.services.classification.types import ClassificationDecision, ClassificationFeatures


class LlmClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    page_count: int
    early_text_snippet: str = Field(max_length=500)
    rule_candidates: list[tuple[DocumentClassification, float]] = Field(default_factory=list)
    allowed_types: list[DocumentClassification] = Field(default_factory=list)


class LlmClassificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: DocumentClassification
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=500)


def classify_with_llm_fallback(
    features: ClassificationFeatures,
    *,
    candidates: list[tuple[DocumentClassification, float]],
    enabled: bool,
) -> ClassificationDecision | None:
    """Provider-neutral stub — live LLM deferred per OD-12."""
    if not enabled:
        return None
    # Future: build LlmClassificationRequest, call provider adapter, validate response.
    _ = LlmClassificationRequest(
        filename=features.display_name,
        page_count=features.page_count,
        early_text_snippet=features.early_page_text[:500],
        rule_candidates=candidates,
        allowed_types=list(DocumentClassification),
    )
    return None
