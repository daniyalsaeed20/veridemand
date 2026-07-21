"""Process (queue-admission) request and response contracts."""

from __future__ import annotations

from pydantic import Field

from backend.app.contracts.base import ApiModel
from backend.app.contracts.identifiers import DocumentId
from backend.app.contracts.jobs import JobSummary
from backend.app.contracts.sessions import SessionSnapshot


class ProcessRequest(ApiModel):
    """Request to queue documents for admission.

    When ``document_ids`` is null, all documents currently in the ``uploaded``
    state are queued. When supplied, every id must belong to the session and only
    eligible uploaded documents are queued.
    """

    document_ids: list[DocumentId] | None = Field(
        default=None, description="Specific documents to queue, or null for all uploaded documents."
    )


class IgnoredDocument(ApiModel):
    """A document that was not (re-)queued, with a safe reason."""

    document_id: DocumentId = Field(description="Ignored document identifier.")
    reason: str = Field(
        description="Why the document was not queued (e.g. already queued/terminal)."
    )


class ProcessResponse(ApiModel):
    """Response for a process request (202 Accepted)."""

    queued: list[JobSummary] = Field(description="Newly created admission jobs.")
    ignored: list[IgnoredDocument] = Field(
        description="Documents that were already queued/terminal."
    )
    session: SessionSnapshot = Field(description="Updated session snapshot.")
