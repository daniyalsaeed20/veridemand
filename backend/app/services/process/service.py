"""Phase 3 process orchestration: normalize + native extraction + OCR."""

from __future__ import annotations

import shutil
import threading
from collections.abc import Callable
from pathlib import Path

from app.core.domain_errors import DomainError
from app.core.logging import get_logger
from app.core.server_settings import ServerSettings
from app.models.app_settings import AppSettings
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.enums import (
    DocumentFileType,
    DocumentStatus,
    IssueSeverity,
    IssueStatus,
    SessionStatus,
)
from app.models.issue import Issue
from app.models.process_event import ProcessEvent
from app.models.source_span import SourceSpan
from app.models.source_token import SourceToken
from app.models.taxonomies import ErrorCode
from app.services.classification import ClassificationService
from app.services.documents.convert_docx import (
    ConversionError,
    DocxConverter,
    LibreOfficeConfig,
    convert_docx_with_libreoffice,
)
from app.services.documents.image_pdf import images_to_canonical_pdf
from app.services.documents.thumbnails import ThumbnailError, count_pdf_pages, create_thumbnails
from app.services.extraction.native import extract_document_native
from app.services.extraction.ocr_page import extract_ocr_page
from app.services.extraction.ocr_quality import OcrPageOutcome
from app.services.facts import FactService
from app.services.ocr import OcrCancelledError, OcrUnavailableError
from app.services.session.service import SessionRecord, SessionService
from app.services.session.workspace import new_opaque_id

logger = get_logger(__name__)


class ProcessService:
    def __init__(
        self,
        *,
        session_service: SessionService,
        app_settings: AppSettings,
        server_settings: ServerSettings,
        docx_converter: DocxConverter | None = None,
        classification_service: ClassificationService | None = None,
        fact_service: FactService | None = None,
    ) -> None:
        self._sessions = session_service
        self._settings = app_settings
        self._server = server_settings
        self._docx_converter: DocxConverter = docx_converter or self._default_docx_converter
        self._classification = classification_service
        self._facts = fact_service
        self._threads: dict[str, threading.Thread] = {}
        self._threads_lock = threading.Lock()
        self._test_hooks: dict[str, Callable[[], None]] = {}

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
        """Enqueue background normalize → native → OCR. Returns events so far."""
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
                DocumentStatus.CLASSIFIED,
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
        record.process_cancel_requested = False
        record.cancel_event.clear()
        record.session.status = SessionStatus.PROCESSING
        generation = record.generation
        self._emit(
            record,
            "process.started",
            status="running",
            message="Normalization, native extraction, and OCR started.",
            progress=0.0,
        )
        events_snapshot = [e.model_copy(deep=True) for e in record.events]

        thread = threading.Thread(
            target=self._run_process_job,
            args=(session_id, generation),
            name=f"process-{session_id}",
            daemon=True,
        )
        with self._threads_lock:
            self._threads[session_id] = thread
        thread.start()
        return events_snapshot

    def wait_until_idle(self, session_id: str, *, timeout: float = 300.0) -> None:
        """Test helper: wait for background process thread to finish."""
        with self._threads_lock:
            thread = self._threads.get(session_id)
        if thread is not None:
            thread.join(timeout=timeout)

    def _run_process_job(self, session_id: str, generation: int) -> None:
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
            return

        try:
            docs = list(record.documents.values())
            total = max(len(docs), 1)
            for index, document in enumerate(docs):
                if self._is_cancelled(session_id, generation):
                    self._emit_cancelled(session_id, generation)
                    return
                if document.status not in {
                    DocumentStatus.UPLOADED,
                    DocumentStatus.NORMALIZED,
                    DocumentStatus.READY_FOR_EXTRACTION,
                    DocumentStatus.EXTRACTED,
                    DocumentStatus.CLASSIFIED,
                }:
                    continue
                self._process_document(session_id, generation, document, index, total)

            if self._is_cancelled(session_id, generation):
                self._emit_cancelled(session_id, generation)
                return

            try:
                record = self._sessions.get_record(session_id, touch=False)
            except DomainError:
                return
            if record.generation != generation:
                return
            record.session.status = SessionStatus.REVIEWING

            # Phase 4: classification + sequencing (no OCR rerun)
            if self._classification is not None:
                self._classification.classify_session(session_id, generation)

            if self._is_cancelled(session_id, generation):
                self._emit_cancelled(session_id, generation)
                return

            try:
                record = self._sessions.get_record(session_id, touch=False)
            except DomainError:
                return
            if record.generation != generation:
                return

            # Phase 5: deterministic facts from published spans (no OCR/PDF rerun)
            if self._facts is not None:
                self._emit(
                    record,
                    "fact.extracting",
                    status="running",
                    message="Extracting deterministic facts.",
                    progress=0.92,
                )
                fact_result = self._facts.extract_session_facts(session_id, generation)
                try:
                    record = self._sessions.get_record(session_id, touch=False)
                except DomainError:
                    return
                if record.generation != generation:
                    return
                self._emit(
                    record,
                    "fact.extracted",
                    status="completed",
                    message=(
                        f"Deterministic facts: {len(fact_result.facts)} facts, "
                        f"{len(fact_result.issues)} review items."
                    ),
                    progress=0.98,
                )

            try:
                record = self._sessions.get_record(session_id, touch=False)
            except DomainError:
                return
            if record.generation != generation:
                return
            record.process_completed = True
            self._emit(
                record,
                "process.completed",
                status="completed",
                message="Phase 5 processing completed.",
                progress=1.0,
            )
        except DomainError as exc:
            self._fail_process(session_id, generation, exc.message, exc.error_code)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Process stage failed",
                extra={"extra_fields": {"session_id": session_id}},
            )
            self._fail_process(
                session_id,
                generation,
                "Processing failed unexpectedly.",
                ErrorCode.PROCESS_STAGE_FAILED,
            )
        finally:
            try:
                record = self._sessions.get_record(session_id, touch=False)
                if record.generation == generation:
                    record.process_running = False
            except DomainError:
                pass
            with self._threads_lock:
                self._threads.pop(session_id, None)

    def _fail_process(
        self,
        session_id: str,
        generation: int,
        message: str,
        error_code: str,
    ) -> None:
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
            return
        record.session.status = SessionStatus.FAILED
        self._emit(
            record,
            "process.failed",
            status="failed",
            message=message,
            error_code=error_code,
        )

    def _emit_cancelled(self, session_id: str, generation: int) -> None:
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
            return
        self._emit(
            record,
            "process.cancelled",
            status="cancelled",
            message="Processing cancelled.",
            error_code=ErrorCode.PROCESS_CANCELLED,
        )

    def _is_cancelled(self, session_id: str, generation: int) -> bool:
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return True
        return (
            record.generation != generation
            or record.process_cancel_requested
            or record.deleting
            or record.cancel_event.is_set()
            or record.session.status == SessionStatus.DELETED
        )

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

    def list_issues(self, session_id: str) -> list[Issue]:
        record = self._sessions.get_record(session_id, touch=True)
        return [i.model_copy(deep=True) for i in record.issues]

    def retry_ocr_page(self, session_id: str, document_id: str, page_number: int) -> DocumentPage:
        """Retry OCR for a failed/review page when the document is extracted."""
        record = self._require_document(session_id, document_id)
        if record.process_running:
            raise DomainError(ErrorCode.PROCESS_ALREADY_RUNNING, session_id=session_id)
        pages = record.pages.get(document_id, [])
        page = next((p for p in pages if p.page_number == page_number), None)
        if page is None:
            raise DomainError(ErrorCode.ROUTE_NOT_FOUND, "Page not found.", session_id=session_id)
        if page.ocr_status not in {"failed", "done"} and "low_confidence" not in page.quality_flags:
            raise DomainError(
                ErrorCode.PROCESS_NOT_READY,
                "Page is not eligible for OCR retry.",
                session_id=session_id,
            )
        canonical = record.canonical_paths.get(document_id)
        if canonical is None:
            raise DomainError(
                ErrorCode.ROUTE_NOT_FOUND, "Canonical PDF missing.", session_id=session_id
            )
        generation = record.generation
        rotation = record.page_rotation.get(document_id, {}).get(page_number, 0)
        # Mutate page to pending for retry
        page.ocr_status = "pending"
        page.quality_flags = list(
            dict.fromkeys([*[f for f in page.quality_flags if f != "awaiting_ocr"], "awaiting_ocr"])
        )
        self._run_ocr_for_page(
            session_id,
            generation,
            document_id,
            page,
            canonical,
            rotation,
            base_progress=0.9,
        )
        return self.get_page(session_id, document_id, page_number)

    def _process_document(
        self,
        session_id: str,
        generation: int,
        document: Document,
        index: int,
        total: int,
    ) -> None:
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
            return

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
            canonical = self._normalize_document(
                record, document, session_id=session_id, generation=generation
            )
            self._emit(
                record,
                "document.normalize.completed",
                document_id=doc_id,
                status="normalized",
                progress=base_progress + 0.15 / max(total, 1),
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

        if self._is_cancelled(session_id, generation):
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

        if self._is_cancelled(session_id, generation):
            return

        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
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
            if result.page.route.value == "manual_review":
                self._add_issue(
                    record,
                    issue_type="extraction.unreadable_page",
                    severity=IssueSeverity.AMBER,
                    title="Blank or unreadable page",
                    explanation="Page produced no usable native text and requires review.",
                    document_id=doc_id,
                    blocking=False,
                )
            self._emit(
                record,
                "document.page.processed",
                document_id=doc_id,
                page_number=result.page.page_number,
                status=result.page.route.value,
                progress=base_progress + 0.4 / max(total, 1),
            )

        record.pages[doc_id] = pages
        record.tokens_by_page[doc_id] = tokens_by_page
        record.spans_by_page[doc_id] = spans_by_page
        record.page_rotation[doc_id] = rotations

        # OCR stage for pending pages
        for page in list(pages):
            if self._is_cancelled(session_id, generation):
                return
            needs_ocr = page.ocr_status == "pending" or (
                self._settings.ocr_force_for_tests and page.route.value == "native"
            )
            if not needs_ocr:
                continue
            self._emit(
                record,
                "document.ocr.queued",
                document_id=doc_id,
                page_number=page.page_number,
                status="queued",
                progress=base_progress + 0.5 / max(total, 1),
            )
            rotation = rotations.get(page.page_number, 0)
            self._run_ocr_for_page(
                session_id,
                generation,
                doc_id,
                page,
                canonical,
                rotation,
                base_progress=base_progress + 0.7 / max(total, 1),
                force=bool(self._settings.ocr_force_for_tests and page.route.value == "native"),
            )

        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
            return

        live_pages = record.pages.get(doc_id, pages)
        warning_count = sum(1 for p in live_pages if p.quality_flags)
        live = record.documents[doc_id]
        live.status = DocumentStatus.EXTRACTED
        live.page_count = len(live_pages)
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

    def _run_ocr_for_page(
        self,
        session_id: str,
        generation: int,
        document_id: str,
        page: DocumentPage,
        canonical: Path,
        rotation: int,
        *,
        base_progress: float,
        force: bool = False,
    ) -> None:
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
            return

        self._emit(
            record,
            "document.ocr.render.started",
            document_id=document_id,
            page_number=page.page_number,
            status="rendering",
            progress=base_progress,
        )

        # Capture generation before long OCR (no session lock held)
        try:
            self._emit(
                record,
                "document.ocr.started",
                document_id=document_id,
                page_number=page.page_number,
                status="running",
                progress=base_progress,
            )
            result = extract_ocr_page(
                canonical,
                document_id=document_id,
                page=page,
                settings=self._settings,
                page_rotation=rotation,
                force_ocr=force,
                cancel_event=record.cancel_event,
            )
        except OcrCancelledError:
            self._emit(
                record,
                "document.ocr.cancelled",
                document_id=document_id,
                page_number=page.page_number,
                status="cancelled",
                error_code=ErrorCode.PROCESS_CANCELLED,
            )
            return
        except OcrUnavailableError:
            logger.exception(
                "OCR failed",
                extra={
                    "extra_fields": {
                        "session_id": session_id,
                        "document_id": document_id,
                        "page_number": page.page_number,
                    }
                },
            )
            try:
                record = self._sessions.get_record(session_id, touch=False)
            except DomainError:
                return
            if record.generation != generation:
                return
            failed_page = page.model_copy(
                deep=True,
                update={
                    "ocr_status": "failed",
                    "quality_flags": list(
                        dict.fromkeys(
                            [
                                *[f for f in page.quality_flags if f != "awaiting_ocr"],
                                "low_confidence",
                            ]
                        )
                    ),
                    "token_count": 0,
                    "span_count": 0,
                },
            )
            self._commit_ocr_page(
                record,
                generation,
                document_id,
                failed_page,
                tokens=[],
                spans=[],
                meta=None,
            )
            self._add_issue(
                record,
                issue_type="extraction.unreadable_page",
                severity=IssueSeverity.RED,
                title="OCR failed for page",
                explanation="OCR engine failed; page requires manual review.",
                document_id=document_id,
                blocking=True,
            )
            self._emit(
                record,
                "document.ocr.failed",
                document_id=document_id,
                page_number=page.page_number,
                status="failed",
                error_code=ErrorCode.EXTRACTION_OCR_FAILED,
                progress=base_progress,
            )
            return

        # Re-verify session before commit
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return
        if record.generation != generation:
            return

        meta = {
            "dpi": result.render_meta.dpi,
            "width": result.render_meta.width,
            "height": result.render_meta.height,
            "rotation": result.render_meta.rotation,
            "preprocess_path": result.render_meta.preprocess_path,
            "elapsed_render_ms": result.render_meta.elapsed_render_ms,
            "elapsed_ocr_ms": result.render_meta.elapsed_ocr_ms,
            "retried": result.retried,
        }
        self._commit_ocr_page(
            record,
            generation,
            document_id,
            result.page,
            tokens=result.tokens,
            spans=result.spans,
            meta=meta,
        )

        if result.assessment.issue_type and result.assessment.issue_severity:
            self._add_issue(
                record,
                issue_type=result.assessment.issue_type,
                severity=result.assessment.issue_severity,
                title=result.assessment.issue_title or "OCR page quality issue",
                explanation="OCR page quality requires review.",
                document_id=document_id,
                blocking=result.assessment.outcome in {OcrPageOutcome.FAILED, OcrPageOutcome.BLANK},
            )

        event = "document.ocr.completed"
        status = "done"
        if result.assessment.outcome in {
            OcrPageOutcome.LOW_CONFIDENCE,
            OcrPageOutcome.USABLE_WITH_WARNING,
        }:
            event = "document.ocr.review_required"
            status = "review_required"
        elif result.assessment.outcome in {OcrPageOutcome.FAILED, OcrPageOutcome.BLANK}:
            event = "document.ocr.failed"
            status = "failed"

        if result.retried:
            self._emit(
                record,
                "document.ocr.retry.completed",
                document_id=document_id,
                page_number=page.page_number,
                status="retried",
                progress=base_progress,
            )

        self._emit(
            record,
            event,
            document_id=document_id,
            page_number=page.page_number,
            status=status,
            progress=base_progress,
        )

    def _commit_ocr_page(
        self,
        record: SessionRecord,
        generation: int,
        document_id: str,
        page: DocumentPage,
        *,
        tokens: list[SourceToken],
        spans: list[SourceSpan],
        meta: dict[str, object] | None,
    ) -> None:
        # Hook outside exclusive delete lock so DELETE can progress (Phase 1 pattern).
        self._run_hook("before_ocr_commit")
        if record.generation != generation or record.deleting:
            return
        if record.session.status == SessionStatus.DELETED:
            return
        if document_id not in record.documents:
            return
        pages = record.pages.get(document_id)
        if pages is None:
            return
        replaced = False
        for i, existing in enumerate(pages):
            if existing.page_number == page.page_number:
                pages[i] = page
                replaced = True
                break
        if not replaced:
            pages.append(page)
        tokens_map = record.tokens_by_page.setdefault(document_id, {})
        spans_map = record.spans_by_page.setdefault(document_id, {})
        # Atomic replace for this page (no duplicate accumulation)
        tokens_map[page.page_number] = list(tokens)
        spans_map[page.page_number] = list(spans)
        if meta is not None:
            record.ocr_meta_by_page.setdefault(document_id, {})[page.page_number] = meta

    def _add_issue(
        self,
        record: SessionRecord,
        *,
        issue_type: str,
        severity: IssueSeverity,
        title: str,
        explanation: str,
        document_id: str,
        blocking: bool,
    ) -> None:
        issue = Issue(
            id=new_opaque_id("issue"),
            session_id=record.session.id,
            issue_type=issue_type,
            severity=severity,
            title=title,
            explanation=explanation,
            document_ids=[document_id],
            blocking=blocking,
            status=IssueStatus.OPEN,
        )
        record.issues.append(issue)

    def _normalize_document(
        self,
        record: SessionRecord,
        document: Document,
        *,
        session_id: str,
        generation: int,
    ) -> Path:
        if self._is_cancelled(session_id, generation):
            raise DomainError(
                ErrorCode.PROCESS_CANCELLED,
                "Processing cancelled.",
                session_id=session_id,
            )
        self._run_hook("before_workspace_write")
        source = record.stored_paths.get(document.id)
        if source is None or not source.is_file():
            raise ConversionError("Original upload is missing.", error_code="process_stage_failed")

        derived = record.workspace / "derived"
        if not self._may_write(session_id, generation):
            raise DomainError(
                ErrorCode.PROCESS_CANCELLED,
                "Processing cancelled.",
                session_id=session_id,
            )
        derived.mkdir(parents=True, exist_ok=True)
        work = record.workspace / "work" / document.id
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)

        live = record.documents[document.id]
        canonical: Path

        try:
            if document.file_type == DocumentFileType.PDF:
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
            self._run_hook("before_thumbnail_save")
            if not self._may_write(session_id, generation):
                raise DomainError(
                    ErrorCode.PROCESS_CANCELLED,
                    "Processing cancelled.",
                    session_id=session_id,
                )
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
            derived_pdf = derived / f"{document.id}.pdf"
            if derived_pdf.exists() and document.file_type != DocumentFileType.PDF:
                derived_pdf.unlink(missing_ok=True)
            raise ConversionError(str(exc), error_code="extraction_render_failed") from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _may_write(self, session_id: str, generation: int) -> bool:
        try:
            record = self._sessions.get_record(session_id, touch=False)
        except DomainError:
            return False
        if record.generation != generation or record.deleting:
            return False
        if record.session.status == SessionStatus.DELETED:
            return False
        if record.process_cancel_requested or record.cancel_event.is_set():
            return False
        return True

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
        record.ocr_meta_by_page.pop(document.id, None)

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
