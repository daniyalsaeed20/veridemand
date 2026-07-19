"""In-memory temporary case session service (Phase 1)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock

from app.core.domain_errors import DomainError, UploadFileError
from app.core.logging import get_logger
from app.models.app_settings import AppSettings
from app.models.case_session import CaseSession
from app.models.document import Document
from app.models.enums import DocumentFileType, DocumentStatus, SessionStatus
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
    # Bumped on delete/expire so in-flight commits detect a lost race
    generation: int = 0


@dataclass(frozen=True)
class UploadPrepare:
    session_id: str
    uploads_dir: Path
    generation: int


@dataclass(frozen=True)
class ValidatedUpload:
    display_name: str
    file_type: DocumentFileType
    content_sha256: str
    page_count: int | None
    size_bytes: int
    provisional_path: Path


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
        # Test-only sync hooks (name -> callable). Never used in production paths.
        self._test_hooks: dict[str, Callable[[], None]] = {}

    @property
    def temp_root(self) -> Path:
        return self._temp_root

    def set_test_hook(self, name: str, fn: Callable[[], None] | None) -> None:
        """Install or clear a deterministic race barrier hook (tests only)."""
        if fn is None:
            self._test_hooks.pop(name, None)
        else:
            self._test_hooks[name] = fn

    def _run_hook(self, name: str) -> None:
        hook = self._test_hooks.get(name)
        if hook is not None:
            hook()

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
            record = self._require_live_locked(session_id)
            if touch:
                self._touch_locked(record)
            return record.session.model_copy(deep=True)

    def get_record(self, session_id: str, *, touch: bool = True) -> SessionRecord:
        """Return the live registry record (tests may mutate expiry; production must not)."""
        with self._lock:
            record = self._require_live_locked(session_id)
            if touch:
                self._touch_locked(record)
            return record

    def prepare_upload(self, session_id: str) -> UploadPrepare:
        """Locked: assert live session and return uploads directory + generation token."""
        with self._lock:
            record = self._require_live_locked(session_id)
            self._touch_locked(record)
            if record.session.status == SessionStatus.CREATED:
                record.session.status = SessionStatus.INGESTING
            uploads = record.workspace / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            prep = UploadPrepare(
                session_id=session_id,
                uploads_dir=uploads,
                generation=record.generation,
            )
            self._run_hook("after_prepare")
            return prep

    def commit_upload(self, prepare: UploadPrepare, validated: ValidatedUpload) -> Document:
        """Atomic registration after off-lock validation.

        The before_commit test hook runs *outside* the lock so delete/expiry
        threads can progress without deadlock.
        """
        self._run_hook("before_commit")
        with self._lock:
            record = self._registry.get(prepare.session_id)
            if record is None or record.session.status in {
                SessionStatus.DELETED,
                SessionStatus.EXPIRED,
            }:
                raise DomainError(
                    ErrorCode.SESSION_NOT_FOUND,
                    session_id=prepare.session_id,
                )
            now = datetime.now(UTC)
            if is_expired(record.session, now):
                self._expire_locked(prepare.session_id, record)
                raise DomainError(
                    ErrorCode.SESSION_EXPIRED,
                    session_id=prepare.session_id,
                )
            if record.generation != prepare.generation:
                raise DomainError(
                    ErrorCode.SESSION_NOT_FOUND,
                    session_id=prepare.session_id,
                )

            active_count = sum(
                1 for d in record.documents.values() if d.status != DocumentStatus.REJECTED
            )
            if active_count >= self._settings.max_files_per_session:
                raise UploadFileError(
                    ErrorCode.UPLOAD_FILE_COUNT_EXCEEDED,
                    validated.display_name,
                )

            existing_id = record.hash_index.get(validated.content_sha256)
            if existing_id is None:
                if record.bytes_used + validated.size_bytes > (
                    self._settings.max_total_upload_mb * 1024 * 1024
                ):
                    raise UploadFileError(
                        ErrorCode.UPLOAD_TOTAL_SIZE_EXCEEDED,
                        validated.display_name,
                    )
                if validated.page_count is not None:
                    if record.pages_used + validated.page_count > (
                        self._settings.max_pages_per_session
                    ):
                        raise UploadFileError(
                            ErrorCode.UPLOAD_PAGE_LIMIT_EXCEEDED,
                            validated.display_name,
                        )

            doc_id = new_opaque_id("doc")
            if existing_id is not None:
                owner_path = record.stored_paths[existing_id]
                document = Document(
                    id=doc_id,
                    session_id=prepare.session_id,
                    display_name=validated.display_name,
                    file_type=validated.file_type,
                    content_sha256=validated.content_sha256,
                    page_count=validated.page_count,
                    status=DocumentStatus.DUPLICATE,
                    exclude_from_drafting=False,
                    treat_as_secondary_evidence=False,
                )
                record.documents[doc_id] = document
                record.stored_paths[doc_id] = owner_path
                self._touch_locked(record)
                return document.model_copy(deep=True)

            dest = validated.provisional_path
            if not dest.exists():
                raise UploadFileError(
                    ErrorCode.UPLOAD_CORRUPT_FILE,
                    validated.display_name,
                    message="Upload data was lost before registration.",
                )

            document = Document(
                id=doc_id,
                session_id=prepare.session_id,
                display_name=validated.display_name,
                file_type=validated.file_type,
                content_sha256=validated.content_sha256,
                page_count=validated.page_count,
                status=DocumentStatus.UPLOADED,
                exclude_from_drafting=False,
                treat_as_secondary_evidence=False,
            )
            record.documents[doc_id] = document
            record.stored_paths[doc_id] = dest
            record.hash_index[validated.content_sha256] = doc_id
            record.bytes_used += validated.size_bytes
            if validated.page_count is not None:
                record.pages_used += validated.page_count
            if record.session.status == SessionStatus.CREATED:
                record.session.status = SessionStatus.INGESTING
            self._touch_locked(record)
            logger.info(
                "Document uploaded",
                extra={
                    "extra_fields": {
                        "session_id": prepare.session_id,
                        "document_id": doc_id,
                        "file_type": validated.file_type.value,
                        "size_bytes": validated.size_bytes,
                    }
                },
            )
            return document.model_copy(deep=True)

    def list_documents(self, session_id: str) -> list[Document]:
        with self._lock:
            record = self._require_live_locked(session_id)
            self._touch_locked(record)
            return [d.model_copy(deep=True) for d in record.documents.values()]

    def delete_document(self, session_id: str, document_id: str) -> None:
        """Idempotent: missing document is a no-op success."""
        with self._lock:
            record = self._require_live_locked(session_id)
            self._touch_locked(record)
            document = record.documents.pop(document_id, None)
            if document is None:
                return

            path = record.stored_paths.pop(document_id, None)
            was_owner = record.hash_index.get(document.content_sha256) == document_id

            if was_owner:
                record.hash_index.pop(document.content_sha256, None)
                for other_id, other in record.documents.items():
                    if other.content_sha256 == document.content_sha256:
                        record.hash_index[document.content_sha256] = other_id
                        other.status = DocumentStatus.UPLOADED
                        was_owner = False
                        break

            still_refs = path is not None and any(p == path for p in record.stored_paths.values())
            if was_owner and path is not None and not still_refs:
                path.unlink(missing_ok=True)
                if document.page_count:
                    record.pages_used = max(0, record.pages_used - document.page_count)
                record.bytes_used = self._recompute_bytes_locked(record)

    def delete_session(self, session_id: str) -> None:
        """Idempotent delete: unknown/already-deleted sessions succeed."""
        self._run_hook("before_delete_session")
        with self._lock:
            record = self._registry.pop(session_id, None)
            if record is None:
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
            record.generation += 1
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

    def _require_live_locked(self, session_id: str) -> SessionRecord:
        record = self._registry.get(session_id)
        if record is None or record.session.status == SessionStatus.DELETED:
            raise DomainError(ErrorCode.SESSION_NOT_FOUND, session_id=session_id)

        now = datetime.now(UTC)
        if is_expired(record.session, now) or record.session.status == SessionStatus.EXPIRED:
            self._expire_locked(session_id, record)
            raise DomainError(ErrorCode.SESSION_EXPIRED, session_id=session_id)
        return record

    def _touch_locked(self, record: SessionRecord) -> None:
        now = datetime.now(UTC)
        ttl = timedelta(minutes=self._settings.session_ttl_minutes)
        record.session.last_activity_at = now
        record.session.expires_at = now + ttl

    def _expire_locked(self, session_id: str, record: SessionRecord) -> None:
        record.session.status = SessionStatus.EXPIRED
        record.generation += 1
        try:
            delete_workspace_tree(record.workspace, self._temp_root)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to delete expired workspace",
                extra={"extra_fields": {"session_id": session_id}},
            )
            self._registry.pop(session_id, None)
            raise DomainError(ErrorCode.SESSION_CLEANUP_FAILED, session_id=session_id) from exc
        self._registry.pop(session_id, None)

    def mark_ingesting(self, session_id: str) -> None:
        with self._lock:
            record = self._registry.get(session_id)
            if record and record.session.status == SessionStatus.CREATED:
                record.session.status = SessionStatus.INGESTING

    def _recompute_bytes_locked(self, record: SessionRecord) -> int:
        total = 0
        seen: set[Path] = set()
        for doc_id, path in record.stored_paths.items():
            doc = record.documents.get(doc_id)
            if doc is None or doc.status == DocumentStatus.DUPLICATE:
                continue
            if path in seen or not path.exists():
                continue
            seen.add(path)
            total += path.stat().st_size
        return total
