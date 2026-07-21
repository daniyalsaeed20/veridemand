"""Bulk upload orchestration.

Implements the Phase 1 pipeline per file, in multipart order:

    filename -> extension allowlist -> client-MIME policy -> streamed size
    enforcement -> signature detection -> structural validation -> known-page /
    session-limit decision -> atomic acceptance.

Each accepted file consumes session capacity before the next is considered, so a
later file may be rejected because an earlier sibling used the remaining budget.
Valid files always survive invalid siblings; per-file rejections never leak
paths, parser output, or document content.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from starlette.datastructures import UploadFile

from backend.app.contracts.documents import DocumentSummary
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.identifiers import new_document_id
from backend.app.contracts.progress import ProgressEventType
from backend.app.contracts.uploads import RejectedDocument
from backend.app.sessions.models import RuntimeDocument, RuntimeSession
from backend.app.sessions.service import recompute_session_status
from backend.app.settings.config import Settings
from backend.app.storage.file_store import (
    EmptyUploadError,
    FileStore,
    FileTooLargeError,
    SessionBytesExceededError,
)
from backend.app.uploads import signatures, validators
from backend.app.uploads.filename import normalise_filename
from backend.app.uploads.formats import (
    ALLOWED_CLIENT_MIME,
    EXTENSION_TO_FORMAT,
    FORMAT_MEDIA_TYPE,
)
from backend.app.uploads.rejection import UploadRejected

_HEAD_BYTES = 512


def _read_head(path: Path, size: int = _HEAD_BYTES) -> bytes:
    with path.open("rb") as handle:
        return handle.read(size)


def _safe_client_mime(mime: str | None) -> str | None:
    if not mime:
        return None
    value = mime.strip()
    if not value or len(value) > 100:
        return None
    if not all(32 <= ord(char) < 127 for char in value):
        return None
    return value


class UploadService:
    """Validates and accepts a bulk upload batch for one session."""

    def __init__(self, settings: Settings, file_store: FileStore) -> None:
        self._settings = settings
        self._file_store = file_store

    async def process_batch(
        self, session: RuntimeSession, uploads: Sequence[UploadFile]
    ) -> tuple[list[DocumentSummary], list[RejectedDocument]]:
        accepted: list[DocumentSummary] = []
        rejected: list[RejectedDocument] = []

        async with session.upload_lock:
            for index, upload in enumerate(uploads):
                client_mime = _safe_client_mime(upload.content_type)
                try:
                    summary = await self._process_one(session, upload)
                except UploadRejected as rejection:
                    await session.broker.publish(
                        ProgressEventType.DOCUMENT_REJECTED,
                        message=rejection.message,
                    )
                    rejected.append(
                        RejectedDocument(
                            input_index=index,
                            display_filename=self._safe_display(upload.filename),
                            error_code=rejection.code.value,
                            message=rejection.message,
                            client_media_type=client_mime,
                            detected_format=rejection.detected_format,
                        )
                    )
                else:
                    accepted.append(summary)

            if accepted:
                recompute_session_status(session)

        return accepted, rejected

    async def _process_one(self, session: RuntimeSession, upload: UploadFile) -> DocumentSummary:
        settings = self._settings

        normalised = normalise_filename(
            upload.filename or "", max_length=settings.max_filename_length
        )
        extension = normalised.extension
        fmt = EXTENSION_TO_FORMAT.get(extension)
        if fmt is None:
            raise UploadRejected(
                ErrorCode.UPLOAD_UNSUPPORTED_TYPE, "This file type is not supported."
            )

        client_mime = _safe_client_mime(upload.content_type)
        if client_mime and client_mime not in ALLOWED_CLIENT_MIME[fmt]:
            raise UploadRejected(
                ErrorCode.UPLOAD_MIME_MISMATCH,
                "The declared content type does not match the file extension.",
                detected_format=fmt.value,
            )

        # File-count limit (consumes capacity in input order).
        if len(session.documents) >= settings.max_files_per_session:
            raise UploadRejected(
                ErrorCode.SESSION_LIMIT_EXCEEDED,
                "This session already holds the maximum number of files.",
            )

        document_id = new_document_id()
        remaining_session_bytes = settings.max_session_bytes - session.accepted_bytes
        try:
            staged = await self._file_store.stage_upload(
                upload,
                session_id=session.session_id,
                document_id=document_id,
                chunk_bytes=settings.upload_chunk_bytes,
                max_single_file_bytes=settings.max_single_file_bytes,
                remaining_session_bytes=remaining_session_bytes,
            )
        except EmptyUploadError:
            raise UploadRejected(
                ErrorCode.UPLOAD_EMPTY_FILE, "The uploaded file is empty."
            ) from None
        except FileTooLargeError:
            self._file_store.remove_document_files(session.session_id, document_id, None)
            raise UploadRejected(
                ErrorCode.UPLOAD_TOO_LARGE, "The file exceeds the single-file size limit."
            ) from None
        except SessionBytesExceededError:
            self._file_store.remove_document_files(session.session_id, document_id, None)
            raise UploadRejected(
                ErrorCode.SESSION_LIMIT_EXCEEDED, "The session storage limit would be exceeded."
            ) from None

        try:
            head = _read_head(staged.path)
            if not signatures.signature_matches(head, fmt):
                raise UploadRejected(
                    ErrorCode.UPLOAD_SIGNATURE_MISMATCH,
                    "File contents do not match the file extension.",
                    detected_format=signatures.detect(head),
                )

            structure = validators.validate_structure(staged.path, fmt, settings)

            if structure.page_count is not None:
                projected = session.known_pages + structure.page_count
                if projected > settings.max_pages_per_session:
                    raise UploadRejected(
                        ErrorCode.SESSION_LIMIT_EXCEEDED,
                        "The session page limit would be exceeded.",
                    )
        except UploadRejected:
            self._file_store.remove_document_files(session.session_id, document_id, None)
            raise

        # Atomic acceptance: move into originals, then record the document.
        self._file_store.commit_original(session.session_id, document_id, extension)

        document = RuntimeDocument(
            document_id=document_id,
            display_filename=normalised.display,
            extension=extension,
            format=fmt,
            media_type=FORMAT_MEDIA_TYPE[fmt],
            size_bytes=staged.size_bytes,
            sha256=staged.sha256,
            page_count=structure.page_count,
            page_count_status=structure.page_count_status,
            warnings=list(structure.warnings),
        )
        session.documents[document_id] = document
        session.accepted_bytes += staged.size_bytes
        if structure.page_count is not None:
            session.known_pages += structure.page_count

        await session.broker.publish(
            ProgressEventType.DOCUMENT_UPLOADED,
            document_id=document_id,
            document_status=document.status,
        )
        for _ in document.warnings:
            await session.broker.publish(
                ProgressEventType.DOCUMENT_WARNING,
                document_id=document_id,
                message="This document references an external resource; it will not be fetched.",
            )

        return document.to_summary()

    def _safe_display(self, raw: str | None) -> str | None:
        if not raw:
            return None
        try:
            return normalise_filename(raw, max_length=self._settings.max_filename_length).display
        except UploadRejected:
            return None
