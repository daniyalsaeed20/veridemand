"""Document upload, validation, and session-scoped metadata (Phase 1)."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.core.domain_errors import DomainError, UploadFileError
from app.core.logging import get_logger
from app.models.app_settings import AppSettings
from app.models.document import Document
from app.models.document_upload_batch import DocumentUploadBatch, UploadRejection
from app.models.enums import DocumentStatus, SessionStatus
from app.models.taxonomies import ErrorCode
from app.services.documents.inspect import inspect_and_count_pages
from app.services.documents.validation import (
    detect_signature,
    extension_for,
    hash_file_sha256,
    new_internal_filename,
    sanitize_display_name,
    validate_extension_mime_signature,
)
from app.services.session.service import SessionService
from app.services.session.workspace import new_opaque_id

logger = get_logger(__name__)


class DocumentService:
    def __init__(self, *, session_service: SessionService, app_settings: AppSettings) -> None:
        self._sessions = session_service
        self._settings = app_settings

    async def upload_documents(
        self, session_id: str, files: list[UploadFile]
    ) -> DocumentUploadBatch:
        self._sessions.get_session(session_id, touch=True)
        self._sessions.mark_ingesting(session_id)

        accepted: list[Document] = []
        rejected: list[UploadRejection] = []

        for upload in files:
            display = "unnamed"
            try:
                display = sanitize_display_name(upload.filename)
                doc = await self._ingest_one(session_id, upload, display)
                accepted.append(doc)
            except UploadFileError as exc:
                rejected.append(
                    UploadRejection(
                        display_name=exc.display_name or display,
                        error_code=exc.error_code,
                        message=exc.message,
                    )
                )
            except DomainError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Unexpected upload failure",
                    extra={"extra_fields": {"session_id": session_id}},
                )
                rejected.append(
                    UploadRejection(
                        display_name=display,
                        error_code=ErrorCode.UPLOAD_CORRUPT_FILE,
                        message="This file appears corrupt or unreadable.",
                    )
                )

        return DocumentUploadBatch(accepted=accepted, rejected=rejected)

    async def _ingest_one(self, session_id: str, upload: UploadFile, display_name: str) -> Document:
        record = self._sessions.get_record(session_id, touch=True)
        max_bytes = self._settings.max_file_size_mb * 1024 * 1024
        max_total = self._settings.max_total_upload_mb * 1024 * 1024

        # Count only non-duplicate, non-rejected toward file limit
        active_count = sum(
            1 for d in record.documents.values() if d.status not in {DocumentStatus.REJECTED}
        )
        if active_count >= self._settings.max_files_per_session:
            raise UploadFileError(ErrorCode.UPLOAD_FILE_COUNT_EXCEEDED, display_name)

        ext = extension_for(display_name)
        internal_name = new_internal_filename(ext or ".bin")
        dest = record.workspace / "uploads" / internal_name
        incomplete: Path | None = dest
        size = 0

        try:
            size = await self._stream_to_disk(upload, dest, max_bytes)
            if record.bytes_used + size > max_total:
                raise UploadFileError(ErrorCode.UPLOAD_TOTAL_SIZE_EXCEEDED, display_name)

            signature = detect_signature(dest)
            file_type = validate_extension_mime_signature(
                display_name, upload.content_type, signature
            )
            page_count = inspect_and_count_pages(dest, file_type)

            if page_count is not None:
                if record.pages_used + page_count > self._settings.max_pages_per_session:
                    raise UploadFileError(ErrorCode.UPLOAD_PAGE_LIMIT_EXCEEDED, display_name)

            digest = hash_file_sha256(dest)
            existing_id = record.hash_index.get(digest)
            doc_id = new_opaque_id("doc")

            if existing_id is not None:
                # Exact duplicate: keep metadata, drop new blob, reuse stored path
                dest.unlink(missing_ok=True)
                incomplete = None
                owner_path = record.stored_paths[existing_id]
                document = Document(
                    id=doc_id,
                    session_id=session_id,
                    display_name=display_name,
                    file_type=file_type,
                    content_sha256=digest,
                    page_count=page_count,
                    status=DocumentStatus.DUPLICATE,
                    exclude_from_drafting=False,
                    treat_as_secondary_evidence=False,
                )
                record.documents[doc_id] = document
                record.stored_paths[doc_id] = owner_path
                # duplicates do not increase bytes_used / pages_used
                return document

            document = Document(
                id=doc_id,
                session_id=session_id,
                display_name=display_name,
                file_type=file_type,
                content_sha256=digest,
                page_count=page_count,
                status=DocumentStatus.UPLOADED,
                exclude_from_drafting=False,
                treat_as_secondary_evidence=False,
            )
            record.documents[doc_id] = document
            record.stored_paths[doc_id] = dest
            record.hash_index[digest] = doc_id
            record.bytes_used += size
            if page_count is not None:
                record.pages_used += page_count
            if record.session.status == SessionStatus.CREATED:
                record.session.status = SessionStatus.INGESTING
            incomplete = None
            logger.info(
                "Document uploaded",
                extra={
                    "extra_fields": {
                        "session_id": session_id,
                        "document_id": doc_id,
                        "file_type": file_type.value,
                        "size_bytes": size,
                    }
                },
            )
            return document
        finally:
            if incomplete is not None and incomplete.exists():
                incomplete.unlink(missing_ok=True)

    async def _stream_to_disk(self, upload: UploadFile, dest: Path, max_bytes: int) -> int:
        size = 0
        try:
            with dest.open("wb") as out:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > max_bytes:
                        raise UploadFileError(
                            ErrorCode.UPLOAD_FILE_TOO_LARGE,
                            sanitize_display_name(upload.filename),
                        )
                    out.write(chunk)
        except UploadFileError:
            dest.unlink(missing_ok=True)
            raise
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise UploadFileError(
                ErrorCode.UPLOAD_CORRUPT_FILE,
                sanitize_display_name(upload.filename),
            ) from exc
        finally:
            await upload.close()
        if size == 0:
            dest.unlink(missing_ok=True)
            raise UploadFileError(
                ErrorCode.UPLOAD_CORRUPT_FILE,
                sanitize_display_name(upload.filename),
                message="Empty file.",
            )
        return size

    def list_documents(self, session_id: str) -> list[Document]:
        record = self._sessions.get_record(session_id, touch=True)
        return [d.model_copy(deep=True) for d in record.documents.values()]

    def delete_document(self, session_id: str, document_id: str) -> None:
        """Idempotent: missing document is a no-op success."""
        record = self._sessions.get_record(session_id, touch=True)
        document = record.documents.pop(document_id, None)
        if document is None:
            return

        path = record.stored_paths.pop(document_id, None)
        was_owner = record.hash_index.get(document.content_sha256) == document_id

        if was_owner:
            record.hash_index.pop(document.content_sha256, None)
            # Promote another duplicate to owner if present
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
            record.bytes_used = self._recompute_bytes(record)

    def _recompute_bytes(self, record: object) -> int:
        from app.services.session.service import SessionRecord

        assert isinstance(record, SessionRecord)
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
