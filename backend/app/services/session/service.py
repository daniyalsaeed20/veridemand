"""In-memory temporary case session service (Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock

from app.core.domain_errors import DomainError
from app.core.logging import get_logger
from app.models.app_settings import AppSettings
from app.models.case_session import CaseSession
from app.models.document import Document
from app.models.enums import SessionStatus
from app.models.taxonomies import ErrorCode
from app.services.session.workspace import (
    SESSION_WARNING,
    build_session_workspace,
    delete_workspace_tree,
    is_expired,
    new_opaque_id,
)

logger = get_logger(__name__)


@dataclass
class SessionRecord:
    session: CaseSession
    workspace: Path
    documents: dict[str, Document] = field(default_factory=dict)
    # content_sha256 -> first document id that owns the stored blob
    hash_index: dict[str, str] = field(default_factory=dict)
    # document_id -> absolute path under uploads/ (duplicates may share path)
    stored_paths: dict[str, Path] = field(default_factory=dict)
    bytes_used: int = 0
    pages_used: int = 0


class SessionService:
    def __init__(
        self,
        *,
        app_settings: AppSettings,
        temp_root: Path,
        max_active_sessions: int = 32,
    ) -> None:
        self._settings = app_settings
        self._temp_root = temp_root.resolve()
        self._temp_root.mkdir(parents=True, exist_ok=True)
        self._max_active = max_active_sessions
        self._registry: dict[str, SessionRecord] = {}
        self._lock = RLock()

    @property
    def temp_root(self) -> Path:
        return self._temp_root

    def create_session(self) -> CaseSession:
        with self._lock:
            active = sum(
                1
                for r in self._registry.values()
                if r.session.status not in {SessionStatus.DELETED, SessionStatus.EXPIRED}
            )
            if active >= self._max_active:
                raise DomainError(ErrorCode.SESSION_LIMIT_EXCEEDED)

            now = datetime.now(UTC)
            session_id = new_opaque_id("ses")
            ttl = timedelta(minutes=self._settings.session_ttl_minutes)
            session = CaseSession(
                id=session_id,
                created_at=now,
                expires_at=now + ttl,
                last_activity_at=now,
                status=SessionStatus.CREATED,
                settings={
                    "ocr_render_dpi": self._settings.ocr_render_dpi,
                    "enable_llm_semantic_extraction": self._settings.enable_llm_semantic_extraction,
                },
                warning=SESSION_WARNING,
            )
            try:
                workspace = build_session_workspace(self._temp_root, session_id)
            except OSError as exc:
                logger.error(
                    "Failed to create session workspace",
                    extra={
                        "extra_fields": {
                            "session_id": session_id,
                            "exc_type": type(exc).__name__,
                        }
                    },
                )
                raise DomainError(
                    ErrorCode.SESSION_CLEANUP_FAILED,
                    "The session workspace could not be created.",
                    session_id=session_id,
                ) from exc

            self._registry[session_id] = SessionRecord(session=session, workspace=workspace)
            logger.info(
                "Session created",
                extra={"extra_fields": {"session_id": session_id}},
            )
            return session.model_copy(deep=True)

    def get_session(self, session_id: str, *, touch: bool = True) -> CaseSession:
        with self._lock:
            record = self._registry.get(session_id)
            if record is None or record.session.status == SessionStatus.DELETED:
                raise DomainError(ErrorCode.SESSION_NOT_FOUND, session_id=session_id)

            now = datetime.now(UTC)
            if is_expired(record.session, now) or record.session.status == SessionStatus.EXPIRED:
                self._expire_locked(session_id, record)
                raise DomainError(ErrorCode.SESSION_EXPIRED, session_id=session_id)

            if touch:
                ttl = timedelta(minutes=self._settings.session_ttl_minutes)
                record.session.last_activity_at = now
                record.session.expires_at = now + ttl
            return record.session.model_copy(deep=True)

    def get_record(self, session_id: str, *, touch: bool = True) -> SessionRecord:
        """Return the live registry record after expiry checks (caller must not mutate unsafely)."""
        self.get_session(session_id, touch=touch)
        with self._lock:
            record = self._registry.get(session_id)
            if record is None:
                raise DomainError(ErrorCode.SESSION_NOT_FOUND, session_id=session_id)
            return record

    def delete_session(self, session_id: str) -> None:
        """Idempotent delete: unknown/already-deleted sessions succeed."""
        with self._lock:
            record = self._registry.pop(session_id, None)
            if record is None:
                # Best-effort remove orphaned directory if present
                candidate = self._temp_root / session_id
                if candidate.exists():
                    try:
                        delete_workspace_tree(candidate, self._temp_root)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Orphan workspace cleanup failed",
                            extra={"extra_fields": {"session_id": session_id}},
                        )
                return
            try:
                delete_workspace_tree(record.workspace, self._temp_root)
            except Exception as exc:  # noqa: BLE001
                logger.exception(
                    "Session cleanup failed",
                    extra={"extra_fields": {"session_id": session_id}},
                )
                raise DomainError(
                    ErrorCode.SESSION_CLEANUP_FAILED,
                    session_id=session_id,
                ) from exc
            logger.info(
                "Session deleted",
                extra={"extra_fields": {"session_id": session_id}},
            )

    def cleanup_expired_sessions(self, now: datetime | None = None) -> list[str]:
        """Remove expired sessions. Safe to call repeatedly. Returns cleaned session IDs."""
        clock = now or datetime.now(UTC)
        cleaned: list[str] = []
        with self._lock:
            expired_ids = [
                sid
                for sid, rec in self._registry.items()
                if is_expired(rec.session, clock) or rec.session.status == SessionStatus.EXPIRED
            ]
            for sid in expired_ids:
                record = self._registry.get(sid)
                if record is None:
                    continue
                try:
                    self._expire_locked(sid, record)
                    cleaned.append(sid)
                except Exception:  # noqa: BLE001 — continue remaining
                    logger.exception(
                        "Expired session cleanup failed",
                        extra={"extra_fields": {"session_id": sid}},
                    )
        return cleaned

    def _expire_locked(self, session_id: str, record: SessionRecord) -> None:
        record.session.status = SessionStatus.EXPIRED
        try:
            delete_workspace_tree(record.workspace, self._temp_root)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to delete expired workspace",
                extra={"extra_fields": {"session_id": session_id}},
            )
            # Still remove from registry so paths cannot be reused
            self._registry.pop(session_id, None)
            raise DomainError(ErrorCode.SESSION_CLEANUP_FAILED, session_id=session_id) from exc
        self._registry.pop(session_id, None)

    def mark_ingesting(self, session_id: str) -> None:
        with self._lock:
            record = self._registry.get(session_id)
            if record and record.session.status == SessionStatus.CREATED:
                record.session.status = SessionStatus.INGESTING
