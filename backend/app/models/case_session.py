"""CaseSession entity."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import SessionStatus


class CaseSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    expires_at: datetime
    last_activity_at: datetime
    status: SessionStatus
    settings: dict[str, Any] = Field(default_factory=dict)
    warning: str | None = None

    @field_validator("id")
    @classmethod
    def _prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("id must start with ses_")
        return value

    @field_validator("status")
    @classmethod
    def _no_active(cls, value: SessionStatus) -> SessionStatus:
        # 'active' is not a SessionStatus member; keep guard for legacy inputs.
        if str(value) == "active":
            raise ValueError("SessionStatus 'active' must never be emitted")
        return value
