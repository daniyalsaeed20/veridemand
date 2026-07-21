"""Opaque, unpredictable runtime identifiers and their public contract types.

Session, document and job identifiers are UUID4-based (32 lowercase hex
characters) and therefore unpredictable. They are never derived from filenames,
user metadata, file hashes, timestamps alone, or global sequential counters.

Event identifiers are sequential *within* an already-unpredictable session
stream: the session id scopes and protects the stream, so a per-session
monotonic sequence is sufficient and stable for SSE ``Last-Event-ID`` replay.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from pydantic import StringConstraints

SESSION_ID_PATTERN: Final = r"^ses_[0-9a-f]{32}$"
DOCUMENT_ID_PATTERN: Final = r"^doc_[0-9a-f]{32}$"
JOB_ID_PATTERN: Final = r"^job_[0-9a-f]{32}$"
EVENT_ID_PATTERN: Final = r"^evt_[0-9]{12}$"

# Public contract types validate identifier shape everywhere they appear.
SessionId = Annotated[str, StringConstraints(pattern=SESSION_ID_PATTERN)]
DocumentId = Annotated[str, StringConstraints(pattern=DOCUMENT_ID_PATTERN)]
JobId = Annotated[str, StringConstraints(pattern=JOB_ID_PATTERN)]
EventId = Annotated[str, StringConstraints(pattern=EVENT_ID_PATTERN)]

_MAX_EVENT_SEQUENCE: Final = 999_999_999_999


def new_session_id() -> str:
    """Return a fresh, unpredictable session identifier."""

    return f"ses_{uuid.uuid4().hex}"


def new_document_id() -> str:
    """Return a fresh, unpredictable document identifier."""

    return f"doc_{uuid.uuid4().hex}"


def new_job_id() -> str:
    """Return a fresh, unpredictable job identifier."""

    return f"job_{uuid.uuid4().hex}"


def format_event_id(sequence: int) -> str:
    """Render a per-session event sequence as a zero-padded event identifier."""

    if sequence < 1 or sequence > _MAX_EVENT_SEQUENCE:
        raise ValueError("Event sequence out of range.")
    return f"evt_{sequence:012d}"
