"""ContractRegistry — export JSON Schema for all contracted entities."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.models.app_settings import AppSettings
from app.models.billing_entry import BillingEntry
from app.models.case_session import CaseSession
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.draft_section import DraftParagraph, DraftSection
from app.models.error_envelope import ErrorEnvelope
from app.models.export_result import ExportArtifact, ExportResult
from app.models.fact import Fact, UserOverride
from app.models.health import HealthCapabilities, HealthResponse
from app.models.issue import Issue, IssueResolution
from app.models.preflight import DraftRef, PreflightFinding, PreflightReport
from app.models.source_span import SourceSpan
from app.models.source_token import SourceToken
from app.models.timeline_event import TimelineEvent
from app.models.user_decision import UserDecision

ENTITY_MODELS: dict[str, type[BaseModel]] = {
    "AppSettings": AppSettings,
    "HealthResponse": HealthResponse,
    "HealthCapabilities": HealthCapabilities,
    "ErrorEnvelope": ErrorEnvelope,
    "CaseSession": CaseSession,
    "Document": Document,
    "DocumentPage": DocumentPage,
    "SourceToken": SourceToken,
    "SourceSpan": SourceSpan,
    "Fact": Fact,
    "UserOverride": UserOverride,
    "Issue": Issue,
    "IssueResolution": IssueResolution,
    "TimelineEvent": TimelineEvent,
    "BillingEntry": BillingEntry,
    "DraftSection": DraftSection,
    "DraftParagraph": DraftParagraph,
    "UserDecision": UserDecision,
    "PreflightFinding": PreflightFinding,
    "PreflightReport": PreflightReport,
    "DraftRef": DraftRef,
    "ExportArtifact": ExportArtifact,
    "ExportResult": ExportResult,
}


class ContractRegistry:
    """Export JSON Schema artifacts for FE generation and contract tests."""

    def json_schemas(self) -> dict[str, dict[str, Any]]:
        return {
            name: model.model_json_schema(mode="serialization")
            for name, model in ENTITY_MODELS.items()
        }
