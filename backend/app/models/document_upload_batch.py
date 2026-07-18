"""DocumentUploadBatch — multi-status upload response (Phase 1)."""

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import Document


class UploadRejection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1)
    error_code: str
    message: str


class DocumentUploadBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: list[Document] = Field(default_factory=list)
    rejected: list[UploadRejection] = Field(default_factory=list)
