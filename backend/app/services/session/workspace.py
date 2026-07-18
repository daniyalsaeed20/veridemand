"""Session workspace helpers (paths stay server-only)."""

from __future__ import annotations

import secrets
import shutil
from datetime import datetime
from pathlib import Path

from app.models.case_session import CaseSession

WORKSPACE_SUBDIRS = ("uploads", "derived", "thumbnails", "work")

SESSION_WARNING = (
    "This is a temporary prototype session. Refreshing or losing it may require starting over."
)


def new_opaque_id(prefix: str = "ses") -> str:
    """Return an unpredictable opaque ID with the given prefix."""
    token = secrets.token_urlsafe(18).replace("-", "").replace("_", "")
    return f"{prefix}_{token}"


def build_session_workspace(temp_root: Path, session_id: str) -> Path:
    """Create session workspace under temp_root. Rejects path traversal via session_id."""
    if (
        not session_id.startswith("ses_")
        or "/" in session_id
        or "\\" in session_id
        or ".." in session_id
    ):
        raise ValueError("invalid session_id for workspace")
    root = temp_root.resolve()
    workspace = (root / session_id).resolve()
    ensure_descendant(workspace, root)
    workspace.mkdir(parents=True, exist_ok=True)
    for name in WORKSPACE_SUBDIRS:
        (workspace / name).mkdir(exist_ok=True)
    return workspace


def is_expired(session: CaseSession, now: datetime) -> bool:
    return now >= session.expires_at


def ensure_descendant(path: Path, root: Path) -> None:
    """Raise if path is not under root (after resolve)."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError("path escapes temp root") from exc


def delete_workspace_tree(workspace: Path, temp_root: Path) -> None:
    """Idempotent removal of a session workspace directory."""
    root = temp_root.resolve()
    if not workspace.exists():
        return
    ensure_descendant(workspace, root)
    shutil.rmtree(workspace, ignore_errors=False)
