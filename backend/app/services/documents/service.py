"""Document upload, validation, and session-scoped metadata (Phase 1)."""

from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.core.domain_errors import DomainError, UploadFileError
from app.core.logging import get_logger
from app.models.app_settings import AppSettings
from app.models.document import Document
from app.models.document_upload_batch import DocumentUploadBatch, UploadRejection
from app.models.enums import DocumentStatus
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
from app.services.session.service import SessionService, ValidatedUpload
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
        prepare = self._sessions.prepare_upload(session_id)
        max_bytes = self._settings.max_file_size_mb * 1024 * 1024

        ext = extension_for(display_name)
        internal_name = new_internal_filename(ext or ".bin")
        token = new_opaque_id("tmp").removeprefix("tmp_")
        provisional = prepare.uploads_dir / f".tmp_{token}_{internal_name}"
        dest = prepare.uploads_dir / internal_name
        incomplete: Path | None = provisional

        try:
            size = await self._stream_to_disk(upload, provisional, max_bytes)

            signature = detect_signature(provisional)
            file_type = validate_extension_mime_signature(
                display_name, upload.content_type, signature
            )
            page_count = inspect_and_count_pages(provisional, file_type)
            digest = hash_file_sha256(provisional)

            if dest.exists():
                dest.unlink(missing_ok=True)
            provisional.rename(dest)
            incomplete = dest

            validated = ValidatedUpload(
                display_name=display_name,
                file_type=file_type,
                content_sha256=digest,
                page_count=page_count,
                size_bytes=size,
                provisional_path=dest,
            )
            document = self._sessions.commit_upload(prepare, validated)
            if document.status == DocumentStatus.DUPLICATE:
                # Blob is unused; owner path already registered
                dest.unlink(missing_ok=True)
            incomplete = None
            return document
        finally:
            if incomplete is not None and incomplete.exists():
                incomplete.unlink(missing_ok=True)
            if provisional.exists() and provisional != incomplete:
                provisional.unlink(missing_ok=True)

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
        return self._sessions.list_documents(session_id)

    def delete_document(self, session_id: str, document_id: str) -> None:
        self._sessions.delete_document(session_id, document_id)
