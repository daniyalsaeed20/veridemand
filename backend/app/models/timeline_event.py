"""TimelineEvent entity."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import TimelineEventType


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    session_id: str
    event_type: TimelineEventType
    event_date: str | None = None
    event_time: str | None = None
    date_precision: Literal["exact", "approximate", "unknown"] | None = None
    summary: str
    fact_ids: list[str] = Field(default_factory=list)
    provider_name: str | None = None
    sort_key: str | None = None

    @field_validator("id")
    @classmethod
    def _evt_prefix(cls, value: str) -> str:
        if not value.startswith("evt_"):
            raise ValueError("id must start with evt_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value
