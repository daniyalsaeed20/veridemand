"""Visual OCR service: page selection, visibility probes, worker jobs, publish."""

from __future__ import annotations

import inspect
import logging
import shutil
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.contracts.canonical import CanonicalPageMetadata
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.native import (
    DocumentSourcePolicy,
    NativeDocumentSummary,
    NativePageDecision,
    NativePageResult,
    SourceMode,
    VisualAgreementStatus,
)
from backend.app.contracts.ocr import HandwritingAssessment
from backend.app.contracts.routing import PageRoute
from backend.app.contracts.visual import (
    NativeVisibilityResult,
    VisualDocumentSummary,
    VisualModelInfo,
    VisualPageResult,
    VisualPageStatus,
    VisualPageSummary,
    VisualProcessingStatus,
    VisualProgress,
    VisualWarning,
)
from backend.app.extraction.routing.router import PageRouter
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.models import (
    VisualPageRef,
    VisualWorkerRequest,
)
from backend.app.extraction.visual.renderer import RenderLimits, render_page
from backend.app.extraction.visual.result_store import (
    cleanup_staging,
    delete_results,
    list_published_page_numbers,
    load_page,
    load_summary,
    publish_page_atomic,
    publish_summary_atomic,
    remove_incomplete_page_parts,
)
from backend.app.extraction.visual.visibility import VisibilityThresholds, probe_native_visibility
from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.processing.cancellation import CancellationToken, JobCancelledError
from backend.app.settings.config import Settings
from backend.app.storage import paths as storage_paths

logger = logging.getLogger("veridemand.visual.service")

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

_PHASE4_USER_MESSAGE = (
    "Printed visual OCR complete. Handwriting and final document structure have not been evaluated."
)


def page_requires_visual(page: NativePageResult) -> bool:
    if page.trust.visual_processing_required:
        return True
    if page.decision in {
        NativePageDecision.REJECTED,
        NativePageDecision.ABSENT,
        NativePageDecision.ERROR,
        NativePageDecision.SUPPRESSED_BY_DOCUMENT_ESCALATION,
    }:
        return True
    return page.source_mode in {SourceMode.VISUAL_AUTHORITY, SourceMode.IMAGE_AUTHORITY}


def page_needs_visibility_probe(page: NativePageResult) -> bool:
    return (
        page.decision is NativePageDecision.ACCEPTED
        and page.source_mode is SourceMode.NATIVE_AUTHORITY
        and page.trust.visual_agreement_status is VisualAgreementStatus.NOT_EVALUATED_PHASE_3
    )


def reconcile_document_policy(
    page_modes: list[SourceMode],
    *,
    image_origin_document: bool = False,
) -> DocumentSourcePolicy:
    if not page_modes:
        return DocumentSourcePolicy.VISUAL_AUTHORITY
    unique = set(page_modes)
    if unique == {SourceMode.NATIVE_AUTHORITY}:
        return DocumentSourcePolicy.NATIVE_AUTHORITY
    if unique == {SourceMode.EMBEDDED_OCR_AUTHORITY}:
        return DocumentSourcePolicy.EMBEDDED_OCR_AUTHORITY
    if unique == {SourceMode.IMAGE_AUTHORITY} or (
        image_origin_document
        and SourceMode.NATIVE_AUTHORITY not in unique
        and SourceMode.EMBEDDED_OCR_AUTHORITY not in unique
    ):
        return DocumentSourcePolicy.IMAGE_AUTHORITY
    if unique == {SourceMode.VISUAL_AUTHORITY}:
        return DocumentSourcePolicy.VISUAL_AUTHORITY
    trusted = {SourceMode.NATIVE_AUTHORITY, SourceMode.EMBEDDED_OCR_AUTHORITY}
    visualish = {SourceMode.VISUAL_AUTHORITY, SourceMode.IMAGE_AUTHORITY}
    if unique & trusted and unique & visualish:
        return DocumentSourcePolicy.MIXED_AUTHORITY
    if unique <= trusted and len(unique) > 1:
        return DocumentSourcePolicy.MIXED_AUTHORITY
    if SourceMode.NATIVE_AUTHORITY in unique and (
        SourceMode.VISUAL_AUTHORITY in unique or SourceMode.IMAGE_AUTHORITY in unique
    ):
        return DocumentSourcePolicy.MIXED_AUTHORITY
    return DocumentSourcePolicy.VISUAL_AUTHORITY


class VisualOcrService:
    """Orchestrates Phase 4 visual processing for one document job."""

    def __init__(self, settings: Settings, worker_manager: OcrWorkerManager | None = None) -> None:
        self._settings = settings
        self._worker = worker_manager or OcrWorkerManager(settings)

    @property
    def worker_manager(self) -> OcrWorkerManager:
        return self._worker

    def load_summary(self, session_id: str, document_id: str) -> VisualDocumentSummary | None:
        path = storage_paths.visual_results_dir(self._settings.temp_root, session_id, document_id)
        return load_summary(path)

    def load_page(
        self, session_id: str, document_id: str, page_number: int
    ) -> VisualPageResult | None:
        path = storage_paths.visual_results_dir(self._settings.temp_root, session_id, document_id)
        return load_page(path, page_number)

    def cleanup_staging(self, session_id: str, job_id: str) -> None:
        cleanup_staging(
            storage_paths.staging_visual_dir(self._settings.temp_root, session_id, job_id)
        )

    def delete_results(self, session_id: str, document_id: str) -> None:
        delete_results(
            storage_paths.visual_results_dir(self._settings.temp_root, session_id, document_id)
        )

    def publish_terminal_failure_summary(
        self,
        *,
        session_id: str,
        document_id: str,
        page_count: int,
        error_code: str,
        canonical_document_available: bool,
        native_pages_retained: int = 0,
        native_pages_downgraded: int = 0,
        pages_selected: int = 0,
        status: VisualProcessingStatus = VisualProcessingStatus.VISUAL_PROCESSING_FAILED,
        user_status_message: str = "Visual OCR could not complete.",
    ) -> VisualDocumentSummary:
        """Atomically publish a terminal visual summary after any failed attempt.

        Contains no document text. Always callable so GET /visual/summary returns
        200 after a visual attempt rather than 404.
        """

        results = storage_paths.visual_results_dir(
            self._settings.temp_root, session_id, document_id
        )
        results.mkdir(parents=True, exist_ok=True)
        now = datetime.now(UTC)
        summary = VisualDocumentSummary(
            document_id=document_id,
            visual_processing_status=status,
            page_count=max(0, page_count),
            pages_selected=max(0, pages_selected),
            pages_completed=0,
            pages_no_text=0,
            pages_failed=max(1, pages_selected) if pages_selected else 1,
            pages_cancelled=0,
            native_pages_retained=max(0, native_pages_retained),
            native_pages_downgraded=max(0, native_pages_downgraded),
            visual_result_available=False,
            handwriting_assessment_pending=True,
            final_result_available=False,
            canonical_document_available=canonical_document_available,
            progress=VisualProgress(
                percent=65,
                pages_completed=0,
                pages_total=max(0, page_count),
            ),
            warnings=[
                VisualWarning(
                    code=error_code,
                    message=user_status_message,
                )
            ],
            error_codes=[error_code],
            created_at=now,
            completed_at=now,
            user_status_message=user_status_message,
        )
        publish_summary_atomic(summary, results)
        return summary

    def suppress_native_page_text(self, page: NativePageResult) -> NativePageResult:
        """Remove public native words/chars after visibility downgrade."""

        trust = page.trust.model_copy(
            update={
                "visual_agreement_status": VisualAgreementStatus.EVALUATED_PHASE_4_VISIBILITY,
                "visual_processing_required": True,
                "native_result_available": False,
                "source_mode": SourceMode.VISUAL_AUTHORITY,
                "decision": NativePageDecision.REJECTED,
                "hard_rejection": True,
                "reason_codes": list(
                    dict.fromkeys(
                        [
                            *page.trust.reason_codes,
                            "native_text_not_visually_present",
                            "visual_agreement_required",
                            "native_text_rejected",
                        ]
                    )
                ),
            }
        )
        return page.model_copy(
            update={
                "decision": NativePageDecision.REJECTED,
                "source_mode": SourceMode.VISUAL_AUTHORITY,
                "trust": trust,
                "words": [],
                "characters": [],
                "provisional_native_text": None,
            }
        )

    async def process_document(
        self,
        *,
        session_id: str,
        document_id: str,
        job_id: str,
        canonical_pdf: Path,
        canonical_pages: list[CanonicalPageMetadata],
        native_summary: NativeDocumentSummary,
        native_pages: dict[int, NativePageResult],
        cancel_token: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> VisualDocumentSummary:
        created_at = datetime.now(UTC)
        staging = storage_paths.staging_visual_dir(self._settings.temp_root, session_id, job_id)
        results = storage_paths.visual_results_dir(
            self._settings.temp_root, session_id, document_id
        )
        staging.mkdir(parents=True, exist_ok=True)
        if results.exists():
            shutil.rmtree(results, ignore_errors=True)
        results.mkdir(parents=True, exist_ok=True)

        page_by_number = {p.page_number: p for p in canonical_pages}
        selected: list[int] = []
        retained_native: set[int] = set()
        downgraded: set[int] = set()
        embedded_verified: set[int] = set()
        targeted_repair_pages: set[int] = set()
        visual_no_text_pages: set[int] = set()
        visibility_by_page: dict[int, NativeVisibilityResult] = {}
        published: dict[int, VisualPageResult] = {}
        router = PageRouter(self._settings)
        hybrid = self._settings.hybrid_page_routing_enabled

        async def _progress(payload: dict[str, Any]) -> None:
            if on_progress is not None:
                result = on_progress(payload)
                if inspect.isawaitable(result):
                    await result

        def _render_probe(page_number: int):
            meta = page_by_number[page_number]
            limits = RenderLimits(
                target_dpi=float(self._settings.ocr_visibility_probe_dpi),
                min_effective_dpi=float(self._settings.ocr_visibility_probe_dpi),
                max_render_pixels=self._settings.ocr_max_render_pixels,
                max_render_side_pixels=self._settings.ocr_max_render_side_pixels,
                dimension_tolerance_points=self._settings.canonical_page_dimension_tolerance_points,
            )
            return render_page(
                canonical_pdf,
                page_number=page_number,
                page_width_points=meta.width_points,
                page_height_points=meta.height_points,
                limits=limits,
            )

        # Phase 4 visibility probes (always) + Phase 4.5 hybrid routing.
        for page_number, native_page in sorted(native_pages.items()):
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            probe_enabled = self._settings.native_visibility_probe_enabled
            vis: NativeVisibilityResult | None = None
            probe_image = None
            rendered = None

            needs_probe_image = (page_needs_visibility_probe(native_page) and probe_enabled) or (
                hybrid and (page_requires_visual(native_page) or bool(native_page.words))
            )
            if needs_probe_image:
                rendered = _render_probe(page_number)
                probe_image = rendered.image

            try:
                needs_visibility = (
                    page_needs_visibility_probe(native_page)
                    and probe_enabled
                    and probe_image is not None
                )
                if needs_visibility:
                    await _progress(
                        {
                            "type": "native_visibility_started",
                            "page_number": page_number,
                        }
                    )
                    vis = probe_native_visibility(
                        probe_image,
                        native_page,
                        thresholds=VisibilityThresholds(
                            min_words=self._settings.native_visibility_min_words,
                            min_visible_word_ratio=self._settings.native_visibility_min_visible_word_ratio,
                            min_region_variance=self._settings.native_visibility_min_region_variance,
                            min_edge_density=self._settings.native_visibility_min_edge_density,
                        ),
                    )
                    visibility_by_page[page_number] = vis
                    if vis.downgraded:
                        downgraded.add(page_number)
                        native_pages[page_number] = self.suppress_native_page_text(native_page)
                        native_page = native_pages[page_number]
                        await _progress(
                            {
                                "type": "native_visibility_rejected",
                                "page_number": page_number,
                                "reason_codes": vis.reason_codes,
                            }
                        )
                    else:
                        await _progress(
                            {
                                "type": "native_visibility_supported",
                                "page_number": page_number,
                            }
                        )

                if hybrid:
                    await _progress(
                        {
                            "type": "page_route_started",
                            "page_number": page_number,
                        }
                    )
                    plan = router.decide(
                        native_page,
                        document_id=document_id,
                        visibility=vis,
                        page_image=probe_image,
                        recognise_crop=None,  # recognition checks run when OCR worker available
                    )
                    decision = plan.decision
                    await _progress(
                        {
                            "type": "page_route_completed",
                            "page_number": page_number,
                            "route": decision.route.value,
                            "reason_codes": decision.reason_codes,
                        }
                    )

                    if decision.route is PageRoute.DIGITAL_NATIVE:
                        retained_native.add(page_number)
                        published[page_number] = VisualPageResult(
                            page_number=page_number,
                            status=VisualPageStatus.SKIPPED_NATIVE_RETAINED,
                            source_mode=SourceMode.NATIVE_AUTHORITY,
                            native_visibility_result=vis,
                            page_route=decision.route.value,
                            route_reason_codes=list(decision.reason_codes),
                            visual_result_available=False,
                            visual_processing_attempted=False,
                            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        )
                        publish_page_atomic(published[page_number], results)
                        await _progress(
                            {
                                "type": "operation_skipped",
                                "page_number": page_number,
                                "operation": "full_visual_ocr",
                                "operation_status": "skipped",
                                "reason_code": "trusted_digital_native_text",
                            }
                        )
                    elif decision.route is PageRoute.EMBEDDED_OCR_VERIFIED:
                        # Without recognition spot-check worker, require visual agreement
                        # only; re-check with recognition when OCR is enabled below.
                        embedded_verified.add(page_number)
                        retained_native.add(page_number)
                        published[page_number] = VisualPageResult(
                            page_number=page_number,
                            status=VisualPageStatus.SKIPPED_EMBEDDED_OCR_VERIFIED,
                            source_mode=SourceMode.EMBEDDED_OCR_AUTHORITY,
                            native_visibility_result=vis,
                            page_route=decision.route.value,
                            route_reason_codes=list(decision.reason_codes),
                            visual_agreement_score=decision.visual_agreement_score,
                            recognition_agreement_score=decision.recognition_agreement_score,
                            visual_result_available=False,
                            visual_processing_attempted=False,
                            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        )
                        publish_page_atomic(published[page_number], results)
                        await _progress(
                            {
                                "type": "embedded_ocr_verified",
                                "page_number": page_number,
                                "route": decision.route.value,
                            }
                        )
                    elif decision.route is PageRoute.EMBEDDED_OCR_TARGETED_REPAIR:
                        # Escalate to full OCR when recognition-only repair worker
                        # is unavailable in this process; mark for selection.
                        repair_ok = (
                            self._settings.targeted_region_repair_enabled
                            and self._settings.ocr_enabled
                        )
                        if repair_ok:
                            targeted_repair_pages.add(page_number)
                        selected.append(page_number)
                        await _progress(
                            {
                                "type": "embedded_ocr_targeted_repair_started",
                                "page_number": page_number,
                            }
                        )
                    elif decision.route is PageRoute.VISUAL_NO_TEXT:
                        visual_no_text_pages.add(page_number)
                        published[page_number] = VisualPageResult(
                            page_number=page_number,
                            status=VisualPageStatus.COMPLETED_NO_TEXT,
                            source_mode=SourceMode.VISUAL_AUTHORITY,
                            page_route=decision.route.value,
                            route_reason_codes=list(decision.reason_codes),
                            visual_result_available=True,
                            visual_processing_attempted=True,
                            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        )
                        publish_page_atomic(published[page_number], results)
                        await _progress(
                            {
                                "type": "visual_no_text_completed",
                                "page_number": page_number,
                            }
                        )
                    elif decision.route is PageRoute.FULL_VISUAL_OCR or page_requires_visual(
                        native_page
                    ):
                        selected.append(page_number)
                    elif native_page.decision is NativePageDecision.ACCEPTED and not vis:
                        retained_native.add(page_number)
                        published[page_number] = VisualPageResult(
                            page_number=page_number,
                            status=VisualPageStatus.SKIPPED_NATIVE_RETAINED,
                            source_mode=SourceMode.NATIVE_AUTHORITY,
                            page_route=PageRoute.DIGITAL_NATIVE.value,
                            visual_result_available=False,
                            visual_processing_attempted=False,
                            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        )
                        publish_page_atomic(published[page_number], results)
                else:
                    # Legacy Phase 4 selection (hybrid disabled).
                    if vis is not None and not vis.downgraded and page_number not in downgraded:
                        retained_native.add(page_number)
                        published[page_number] = VisualPageResult(
                            page_number=page_number,
                            status=VisualPageStatus.SKIPPED_NATIVE_RETAINED,
                            source_mode=SourceMode.NATIVE_AUTHORITY,
                            native_visibility_result=vis,
                            visual_result_available=False,
                            visual_processing_attempted=False,
                            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        )
                        publish_page_atomic(published[page_number], results)
                    elif page_number in downgraded or page_requires_visual(native_page):
                        selected.append(page_number)
                    elif native_page.decision is NativePageDecision.ACCEPTED:
                        retained_native.add(page_number)
                        published[page_number] = VisualPageResult(
                            page_number=page_number,
                            status=VisualPageStatus.SKIPPED_NATIVE_RETAINED,
                            source_mode=SourceMode.NATIVE_AUTHORITY,
                            visual_result_available=False,
                            visual_processing_attempted=False,
                            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        )
                        publish_page_atomic(published[page_number], results)
            finally:
                if rendered is not None:
                    rendered.image.close()

        selected = sorted(set(selected))
        await _progress(
            {
                "type": "visual_pages_selected",
                "pages_selected": len(selected),
                "pages_total": len(canonical_pages),
                "native_pages_retained": len(retained_native),
                "embedded_ocr_pages_verified": len(embedded_verified),
                "targeted_repair_pages_selected": len(targeted_repair_pages),
                "full_ocr_pages_selected": len(selected),
            }
        )

        if selected and not self._settings.ocr_enabled:
            for n in selected:
                selected_native = native_pages.get(n)
                source_mode = (
                    selected_native.source_mode
                    if selected_native is not None
                    else SourceMode.VISUAL_AUTHORITY
                )
                page = VisualPageResult(
                    page_number=n,
                    status=VisualPageStatus.FAILED,
                    source_mode=source_mode,
                    native_visibility_result=visibility_by_page.get(n),
                    visual_result_available=False,
                    visual_processing_attempted=False,
                    handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                    error_code=ErrorCode.OCR_WORKER_NOT_READY.value,
                )
                publish_page_atomic(page, results)
                published[n] = page
                await _progress({"type": "page.failed", "page_number": n})
        elif selected:
            config = self._worker.config_from_settings()
            page_refs = [
                VisualPageRef(
                    page_number=n,
                    width_points=page_by_number[n].width_points,
                    height_points=page_by_number[n].height_points,
                    intrinsic_rotation=page_by_number[n].intrinsic_rotation,
                    source_type=page_by_number[n].source_type.value,
                )
                for n in selected
            ]
            max_attempts = 2
            last_error: VisualOcrError | None = None
            for attempt in range(1, max_attempts + 1):
                published_nums = set(list_published_page_numbers(results))
                remaining = [n for n in selected if n not in published_nums]
                if not remaining:
                    break
                remove_incomplete_page_parts(results)
                current_attempt = attempt
                request = VisualWorkerRequest(
                    request_id=f"{job_id}:a{attempt}",
                    session_id=session_id,
                    document_id=document_id,
                    job_id=job_id,
                    canonical_pdf_path=str(canonical_pdf),
                    pages=[ref for ref in page_refs if ref.page_number in remaining],
                    page_output_dir=str(results),
                    staging_dir=str(staging),
                    config=config,
                    skip_page_numbers=tuple(sorted(published_nums)),
                )

                async def _worker_progress(
                    payload: dict[str, Any], *, _attempt: int = current_attempt
                ) -> None:
                    payload = dict(payload)
                    payload.setdefault("attempt_number", _attempt)
                    payload.setdefault("max_attempts", max_attempts)
                    await _progress(payload)

                await _progress(
                    {
                        "type": "worker.retry" if attempt > 1 else "worker.request",
                        "attempt_number": attempt,
                        "max_attempts": max_attempts,
                        "pages_remaining": len(remaining),
                        "worker_generation": getattr(self._worker, "generation", None),
                    }
                )
                try:
                    await self._worker.process_document(
                        request,
                        cancel_token=cancel_token,
                        on_progress=_worker_progress,
                        attempt_number=attempt,
                    )
                    last_error = None
                    break
                except JobCancelledError:
                    raise
                except VisualOcrError as exc:
                    last_error = exc
                    recoverable = exc.code in {
                        ErrorCode.OCR_WORKER_CRASHED,
                        ErrorCode.OCR_PAGE_TIMEOUT,
                        ErrorCode.OCR_DOCUMENT_TIMEOUT,
                        ErrorCode.OCR_WORKER_NOT_READY,
                    }
                    await _progress(
                        {
                            "type": "worker.request_failed",
                            "attempt_number": attempt,
                            "max_attempts": max_attempts,
                            "reason_code": exc.code.value,
                            "recoverable": recoverable,
                        }
                    )
                    if not recoverable or attempt >= max_attempts:
                        break
                    # Manager already restarted on recoverable loss; retry remaining pages.
                    continue

            for n in selected:
                page_result = load_page(results, n)
                if page_result is not None:
                    if n in visibility_by_page and page_result.native_visibility_result is None:
                        page_result = page_result.model_copy(
                            update={"native_visibility_result": visibility_by_page[n]}
                        )
                        publish_page_atomic(page_result, results)
                    published[n] = page_result
                elif last_error is not None:
                    selected_native = native_pages.get(n)
                    source_mode = (
                        selected_native.source_mode
                        if selected_native is not None
                        else SourceMode.VISUAL_AUTHORITY
                    )
                    failed_page = VisualPageResult(
                        page_number=n,
                        status=VisualPageStatus.FAILED,
                        source_mode=source_mode,
                        native_visibility_result=visibility_by_page.get(n),
                        visual_result_available=False,
                        visual_processing_attempted=True,
                        handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
                        error_code=last_error.code.value,
                    )
                    publish_page_atomic(failed_page, results)
                    published[n] = failed_page
                    await _progress(
                        {
                            "type": "page.failed",
                            "page_number": n,
                            "reason_code": last_error.code.value,
                            "failed_operation": last_error.operation or "paddle_ocr_pipeline",
                            "attempt_number": max_attempts,
                            "max_attempts": max_attempts,
                        }
                    )

        # Ensure every canonical page has a row.
        for meta in canonical_pages:
            if meta.page_number not in published:
                published[meta.page_number] = VisualPageResult(
                    page_number=meta.page_number,
                    status=VisualPageStatus.PENDING,
                    source_mode=SourceMode.VISUAL_AUTHORITY,
                    visual_result_available=False,
                    visual_processing_attempted=False,
                )

        page_modes: list[SourceMode] = []
        completed = no_text = failed = cancelled = 0
        for page in published.values():
            page_modes.append(page.source_mode)
            if page.status is VisualPageStatus.COMPLETED:
                completed += 1
            elif page.status is VisualPageStatus.COMPLETED_NO_TEXT:
                no_text += 1
            elif page.status is VisualPageStatus.FAILED:
                failed += 1
            elif page.status is VisualPageStatus.CANCELLED:
                cancelled += 1
            elif page.status is VisualPageStatus.SKIPPED_NATIVE_RETAINED:
                completed += 0  # retained native — not OCR completed
            elif page.status is VisualPageStatus.SKIPPED_EMBEDDED_OCR_VERIFIED:
                completed += 0
            elif page.status is VisualPageStatus.TARGETED_REPAIR_COMPLETED:
                completed += 1

        if not selected and not visual_no_text_pages:
            status = VisualProcessingStatus.NOT_REQUIRED
        elif not selected and visual_no_text_pages:
            status = VisualProcessingStatus.VISUAL_PROCESSING_COMPLETE
        elif failed and (completed + no_text) > 0:
            status = VisualProcessingStatus.VISUAL_PROCESSING_PARTIAL
        elif failed and (completed + no_text) == 0:
            status = VisualProcessingStatus.VISUAL_PROCESSING_FAILED
        elif cancelled:
            status = VisualProcessingStatus.CANCELLED
        else:
            status = VisualProcessingStatus.VISUAL_PROCESSING_COMPLETE

        policy = reconcile_document_policy(page_modes)
        model_info = VisualModelInfo(
            detection_model_name=self._settings.ocr_detection_model_name,
            recognition_model_name=self._settings.ocr_recognition_model_name,
            device=self._settings.ocr_device,
            engine=self._settings.ocr_engine,
        )
        summaries = [
            VisualPageSummary(
                page_number=p.page_number,
                status=p.status,
                source_mode=p.source_mode,
                line_count=p.line_count,
                word_count=p.word_count,
                visual_result_available=p.visual_result_available,
                native_retained=p.page_number in retained_native,
                native_downgraded=p.page_number in downgraded,
                average_recognition_score=p.average_recognition_score,
                error_code=p.error_code,
            )
            for p in sorted(published.values(), key=lambda item: item.page_number)
        ]
        visual_available = any(p.visual_result_available for p in published.values())
        full_ocr_done = sum(
            1
            for p in published.values()
            if p.status
            in {
                VisualPageStatus.COMPLETED,
                VisualPageStatus.COMPLETED_NO_TEXT,
                VisualPageStatus.FAILED,
            }
            and p.page_number in selected
        )
        summary = VisualDocumentSummary(
            document_id=document_id,
            visual_processing_status=status,
            page_count=len(canonical_pages),
            pages_selected=len(selected),
            pages_completed=completed + no_text,
            pages_no_text=no_text + len(visual_no_text_pages),
            pages_failed=failed,
            pages_cancelled=cancelled,
            native_pages_retained=len(retained_native),
            native_pages_downgraded=len(downgraded),
            embedded_ocr_pages_verified=len(embedded_verified),
            targeted_repair_pages=len(targeted_repair_pages),
            full_ocr_pages=len(selected),
            visual_no_text_pages=len(visual_no_text_pages),
            visual_result_available=visual_available,
            handwriting_assessment_pending=True,
            final_result_available=False,
            canonical_document_available=True,
            document_source_policy=policy,
            progress=VisualProgress(
                percent=65,
                pages_completed=completed + no_text + len(retained_native) + len(embedded_verified),
                pages_total=len(canonical_pages),
            ),
            model_info=model_info,
            page_summaries=summaries,
            warnings=[],
            created_at=created_at,
            completed_at=datetime.now(UTC),
            user_status_message=_PHASE4_USER_MESSAGE,
        )
        _ = full_ocr_done
        await _progress({"type": "visual_summary_publication.started"})
        publish_summary_atomic(summary, results)
        await _progress({"type": "visual_summary_publication.completed"})
        cleanup_staging(staging)
        return summary
