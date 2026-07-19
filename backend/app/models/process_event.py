"""Process progress event (session-scoped; additive to Phase 2 APIs)."""

from pydantic import BaseModel, ConfigDict, Field


class ProcessEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=0)
    event: str
    session_id: str
    document_id: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    status: str | None = None
    message: str | None = None
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    error_code: str | None = None
