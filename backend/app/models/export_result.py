"""ExportResult / ExportArtifact entities."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import ExportKind


class ExportArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    content_type: str
    status: Literal["available", "failed", "skipped"]
    filename: str | None = None
    warning: str | None = None

    @field_validator("artifact_id")
    @classmethod
    def _art_prefix(cls, value: str) -> str:
        if not value.startswith("art_"):
            raise ValueError("artifact_id must start with art_")
        return value

    @field_validator("filename")
    @classmethod
    def _basename_only(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if "/" in value or "\\" in value or ":" in value:
            raise ValueError("filename must be a basename only, never a path")
        return value


class ExportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    export_id: str
    session_id: str
    draft_id: str
    kind: ExportKind
    docx: ExportArtifact
    pdf_preview: ExportArtifact | None = None
    preflight_id: str
    created_at: datetime

    @field_validator("export_id")
    @classmethod
    def _exp_prefix(cls, value: str) -> str:
        if not value.startswith("exp_"):
            raise ValueError("export_id must start with exp_")
        return value

    @field_validator("session_id")
    @classmethod
    def _ses_prefix(cls, value: str) -> str:
        if not value.startswith("ses_"):
            raise ValueError("session_id must start with ses_")
        return value

    @field_validator("draft_id")
    @classmethod
    def _draft_prefix(cls, value: str) -> str:
        if not value.startswith("draft_"):
            raise ValueError("draft_id must start with draft_")
        return value

    @field_validator("preflight_id")
    @classmethod
    def _preflight_prefix(cls, value: str) -> str:
        if not value.startswith("preflight_"):
            raise ValueError("preflight_id must start with preflight_")
        return value
