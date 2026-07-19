"""Phase 2 process orchestration: normalize + native extraction."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.core.domain_errors import DomainError
from app.core.logging import get_logger
from app.core.server_settings import ServerSettings
from app.models.app_settings import AppSettings
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.enums import DocumentFileType, DocumentStatus, SessionStatus
from app.models.process_event import ProcessEvent
from app.models.source_span import SourceSpan
from app.models.source_token import SourceToken
from app.models.taxonomies import ErrorCode
from app.services.documents.convert_docx import (
    ConversionError,
    DocxConverter,
    LibreOfficeConfig,
    convert_docx_with_libreoffice,
)
from app.services.documents.image_pdf import images_to_canonical_pdf
from app.services.documents.thumbnails import ThumbnailError, count_pdf_pages, create_thumbnails
from app.services.extraction.native import extract_document_native
from app.services.session.service import SessionRecord, SessionService

logger = get_logger(__name__)


class ProcessService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        app_settings: AppSettings,
        server_settings: ServerSettings,
        docx_converter: DocxConverter | None = None,
    ) -> None:
        self._sessions = session_service
        self._settings = app_settings
        self._server = server_settings
        self._docx_converter: DocxConverter = docx_converter or self._default_docx_converter

    def _default_docx_converter(self, source: Path, output: Path, work: Path) -> Path:
        return convert_docx_with_libreoffice(
            source,
            output,
            work,
            config=LibreOfficeConfig(
                executable=self._server.libreoffice_path,
                timeout_seconds=self._server.libreoffice_timeout_seconds,
            ),
        )

    def set_docx_converter(self, converter: DocxConverter | None) -> None:
        """Tests inject a fake converter; None restores LibreOffice default."""
        self._docx_converter = converter or self._default_docx_converter

    def start_process(self, session_id: str) -> list[ProcessEvent]:
        record = self._sessions.get_record(session_id, touch=True)
        if record.process_running:
            raise DomainError(ErrorCode.PROCESS_ALREADY_RUNNING, session_id=session_id)

        docs = [
            d
            for d in record.documents.values()
            if d.status
            in {
                DocumentStatus.UPLOADED,
                DocumentStatus.NORMALIZED,
                DocumentStatus.READY_FOR_EXTRACTION,
                DocumentStatus.EXTRACTED,
            }
        ]
        if not docs:
            raise DomainError(
                ErrorCode.PROCESS_NOT_READY,
                "No processable documents in this session.",
                session_id=session_id,
            )

        record.process_running = True
        record.process_completed = False
        record.session.status = SessionStatus.PROCESSING
        self._emit(
            record,
            "process.started",
            status="running",
            message="Normalization and native extraction started.",
            progress=0.0,
        )

        try:
            total = len(docs)
            for index, document in enumerate(docs):
                self._process_document(record, document, index, total)
            record.session.status = SessionStatus.REVIEWING
            record.process_completed = True
            self._emit(
                record,
                "process.completed",
                status="completed",
                message="Phase 2 processing completed.",
                progress=1.0,
            )
        except DomainError as exc:
            record.session.status = SessionStatus.FAILED
            self._emit(
                record,
                "process.failed",
                status="failed",
                message=exc.message,
                error_code=exc.error_code,
                progress=None,
            )
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Process stage failed",
                extra={"extra_fields": {"session_id": session_id}},
            )
            record.session.status = SessionStatus.FAILED
            self._emit(
                record,
                "process.failed",
                status="failed",
                message="Processing failed unexpectedly.",
                error_code=ErrorCode.PROCESS_STAGE_FAILED,
            )
            raise DomainError(
                ErrorCode.PROCESS_STAGE_FAILED,
                session_id=session_id,
            ) from exc
        finally:
            record.process_running = False

        return [e.model_copy(deep=True) for e in record.events]

    def list_events(self, session_id: str, *, after: int = -1) -> list[ProcessEvent]:
        record = self._sessions.get_record(session_id, touch=True)
        return [e.model_copy(deep=True) for e in record.events if e.sequence > after]

    def list_pages(self, session_id: str, document_id: str) -> list[DocumentPage]:
        record = self._require_document(session_id, document_id)
        pages = record.pages.get(document_id, [])
        return [p.model_copy(deep=True) for p in pages]

    def get_page(self, session_id: str, document_id: str, page_number: int) -> DocumentPage:
        pages = self.list_pages(session_id, document_id)
        for page in pages:
            if page.page_number == page_number:
                return page
        raise DomainError(
            ErrorCode.ROUTE_NOT_FOUND,
            "Page not found.",
            session_id=session_id,
            document_id=document_id,
        )

    def get_canonical_pdf_path(self, session_id: str, document_id: str) -> Path:
        record = self._require_document(session_id, document_id)
        path = record.canonical_paths.get(document_id)
        if path is None or not path.is_file():
            raise DomainError(
                ErrorCode.ROUTE_NOT_FOUND,
                "Canonical viewing copy is not available.",
                session_id=session_id,
                document_id=document_id,
            )
        self._ensure_under_workspace(path, record.workspace)
        return path

    def get_thumbnail_path(self, session_id: str, document_id: str, page_number: int) -> Path:
        record = self._require_document(session_id, document_id)
        thumb_dir = record.thumbnail_dirs.get(document_id)
        if thumb_dir is None:
            raise DomainError(
                ErrorCode.ROUTE_NOT_FOUND,
                "Thumbnail is not available.",
                session_id=session_id,
                document_id=document_id,
            )
        path = thumb_dir / f"page_{page_number}.png"
        if not path.is_file():
            raise DomainError(
                ErrorCode.ROUTE_NOT_FOUND,
                "Thumbnail is not available.",
                session_id=session_id,
                document_id=document_id,
            )
        self._ensure_under_workspace(path, record.workspace)
        return path

    def list_tokens(self, session_id: str, document_id: str, page_number: int) -> list[SourceToken]:
        record = self._require_document(session_id, document_id)
        by_page = record.tokens_by_page.get(document_id, {})
        tokens = by_page.get(page_number, [])
        return [t.model_copy(deep=True) for t in tokens]

    def list_spans(self, session_id: str, document_id: str, page_number: int) -> list[SourceSpan]:
        record = self._require_document(session_id, document_id)
        by_page = record.spans_by_page.get(document_id, {})
        spans = by_page.get(page_number, [])
        return [s.model_copy(deep=True) for s in spans]

    def _process_document(
        self,
        record: SessionRecord,
        document: Document,
        index: int,
        total: int,
    ) -> None:
        session_id = record.session.id
        doc_id = document.id
        base_progress = index / max(total, 1)
        self._emit(
            record,
            "document.normalize.started",
            document_id=doc_id,
            status="running",
            message="Normalizing document.",
            progress=base_progress,
        )

        try:
            canonical = self._normalize_document(record, document)
            self._emit(
                record,
                "document.normalize.completed",
                document_id=doc_id,
                status="normalized",
                progress=base_progress + 0.3 / max(total, 1),
            )
        except ConversionError as exc:
            self._fail_document(record, document, exc.error_code, str(exc))
            self._emit(
                record,
                "document.normalize.failed",
                document_id=doc_id,
                status="failed",
                message=str(exc),
                error_code=exc.error_code,
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception(
                "Normalization failed",
                extra={"extra_fields": {"session_id": session_id, "document_id": doc_id}},
            )
            self._fail_document(
                record, document, ErrorCode.PROCESS_STAGE_FAILED, "Normalization failed."
            )
            self._emit(
                record,
                "document.normalize.failed",
                document_id=doc_id,
                status="failed",
                message="Normalization failed.",
                error_code=ErrorCode.PROCESS_STAGE_FAILED,
            )
            return

        try:
            results = extract_document_native(
                canonical,
                document_id=doc_id,
                settings=self._settings,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Native extraction failed",
                extra={"extra_fields": {"session_id": session_id, "document_id": doc_id}},
            )
            self._fail_document(
                record,
                document,
                ErrorCode.EXTRACTION_NATIVE_FAILED,
                "Native text extraction failed unexpectedly.",
            )
            self._emit(
                record,
                "document.extract.failed",
                document_id=doc_id,
                status="failed",
                message="Native extraction failed.",
                error_code=ErrorCode.EXTRACTION_NATIVE_FAILED,
            )
            return

        pages: list[DocumentPage] = []
        tokens_by_page: dict[int, list[SourceToken]] = {}
        spans_by_page: dict[int, list[SourceSpan]] = {}
        rotations: dict[int, int] = {}
        warning_count = 0
        for result in results:
            pages.append(result.page)
            tokens_by_page[result.page.page_number] = result.tokens
            spans_by_page[result.page.page_number] = list(result.spans)
            rotations[result.page.page_number] = result.rotation
            if result.page.quality_flags:
                warning_count += 1
            self._emit(
                record,
                "document.page.processed",
                document_id=doc_id,
                page_number=result.page.page_number,
                status=result.page.route.value,
                progress=base_progress + 0.9 / max(total, 1),
            )

        record.pages[doc_id] = pages
        record.tokens_by_page[doc_id] = tokens_by_page
        record.spans_by_page[doc_id] = spans_by_page
        record.page_rotation[doc_id] = rotations

        live = record.documents[doc_id]
        live.status = DocumentStatus.EXTRACTED
        live.page_count = len(pages)
        live.page_quality_warning_count = warning_count
        live.error_code = None
        live.error_message = None

        self._emit(
            record,
            "document.extract.completed",
            document_id=doc_id,
            status="extracted",
            progress=(index + 1) / max(total, 1),
        )

    def _normalize_document(self, record: SessionRecord, document: Document) -> Path:
        source = record.stored_paths.get(document.id)
        if source is None or not source.is_file():
            raise ConversionError("Original upload is missing.", error_code="process_stage_failed")

        derived = record.workspace / "derived"
        derived.mkdir(parents=True, exist_ok=True)
        work = record.workspace / "work" / document.id
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)

        live = record.documents[document.id]
        canonical: Path

        try:
            if document.file_type == DocumentFileType.PDF:
                # Retain original as the canonical viewing copy (do not alter evidence)
                canonical = source
            elif document.file_type == DocumentFileType.DOCX:
                canonical = derived / f"{document.id}.pdf"
                if canonical.exists():
                    canonical.unlink()
                self._docx_converter(source, canonical, work)
            elif document.file_type in {
                DocumentFileType.JPG,
                DocumentFileType.PNG,
                DocumentFileType.TIFF,
            }:
                canonical = derived / f"{document.id}.pdf"
                if canonical.exists():
                    canonical.unlink()
                page_count = images_to_canonical_pdf(source, canonical)
                live.page_count = page_count
            else:
                raise ConversionError(
                    "Unsupported file type for normalization.",
                    error_code="process_stage_failed",
                )

            if not canonical.is_file() or canonical.stat().st_size == 0:
                raise ConversionError(
                    "Canonical viewing copy is missing or empty.",
                    error_code="process_stage_failed",
                )

            page_count = count_pdf_pages(canonical)
            live.page_count = page_count

            thumb_dir = record.workspace / "thumbnails" / document.id
            if thumb_dir.exists():
                shutil.rmtree(thumb_dir, ignore_errors=True)
            create_thumbnails(
                canonical,
                thumb_dir,
                max_width=self._server.thumbnail_max_width,
            )
            record.canonical_paths[document.id] = canonical
            record.thumbnail_dirs[document.id] = thumb_dir
            live.status = DocumentStatus.READY_FOR_EXTRACTION
            live.error_code = None
            live.error_message = None
            return canonical
        except ThumbnailError as exc:
            # Cleanup partial derived outputs (never the original upload)
            derived_pdf = derived / f"{document.id}.pdf"
            if derived_pdf.exists() and document.file_type != DocumentFileType.PDF:
                derived_pdf.unlink(missing_ok=True)
            raise ConversionError(str(exc), error_code="extraction_render_failed") from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _fail_document(
        self,
        record: SessionRecord,
        document: Document,
        error_code: str,
        message: str,
    ) -> None:
        live = record.documents[document.id]
        live.status = DocumentStatus.UPLOADED
        live.error_code = error_code
        live.error_message = message
        # Remove partial derived artifacts (never the original upload)
        canon = record.canonical_paths.pop(document.id, None)
        if canon is not None and "derived" in canon.parts and canon.exists():
            canon.unlink(missing_ok=True)
        thumb_dir = record.thumbnail_dirs.pop(document.id, None)
        if thumb_dir is not None and thumb_dir.exists():
            shutil.rmtree(thumb_dir, ignore_errors=True)
        record.pages.pop(document.id, None)
        record.tokens_by_page.pop(document.id, None)
        record.spans_by_page.pop(document.id, None)
        record.page_rotation.pop(document.id, None)

    def _require_document(self, session_id: str, document_id: str) -> SessionRecord:
        record = self._sessions.get_record(session_id, touch=True)
        if document_id not in record.documents:
            raise DomainError(
                ErrorCode.ROUTE_NOT_FOUND,
                "Document not found.",
                session_id=session_id,
                document_id=document_id,
            )
        return record

    def _ensure_under_workspace(self, path: Path, workspace: Path) -> None:
        resolved = path.resolve()
        root = workspace.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise DomainError(ErrorCode.ROUTE_NOT_FOUND, "Resource not found.") from exc

    def _emit(
        self,
        record: SessionRecord,
        event: str,
        *,
        document_id: str | None = None,
        page_number: int | None = None,
        status: str | None = None,
        message: str | None = None,
        progress: float | None = None,
        error_code: str | None = None,
    ) -> None:
        record.event_sequence += 1
        record.events.append(
            ProcessEvent(
                sequence=record.event_sequence,
                event=event,
                session_id=record.session.id,
                document_id=document_id,
                page_number=page_number,
                status=status,
                message=message,
                progress=progress,
                error_code=error_code,
            )
        )
