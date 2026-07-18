"""UserDecision entity."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import DecisionAction


class UserDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    target_type: Literal["fact", "issue", "document", "span", "billing", "draft"]
    target_id: str
    action: DecisionAction
    old_value: str | dict[str, Any] | None = None
    new_value: str | dict[str, Any] | None = None
    reason: str | None = None
    timestamp: datetime
    actor_role: Literal["paralegal", "attorney", "system"] | None = None

    @field_validator("id")
    @classmethod
    def _dec_prefix(cls, value: str) -> str:
        if not value.startswith("dec_"):
            raise ValueError("id must start with dec_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value
