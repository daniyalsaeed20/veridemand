"""Visual OCR service: page selection, visibility probes, worker jobs, publish."""

from __future__ import annotations

import contextlib
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
from backend.app.contracts.visual import (
    NativeVisibilityResult,
    VisualDocumentSummary,
    VisualModelInfo,
    VisualPageResult,
    VisualPageStatus,
    VisualPageSummary,
    VisualProcessingStatus,
    VisualProgress,
)
from backend.app.extraction.visual.errors import VisualOcrError
from backend.app.extraction.visual.models import (
    VisualPageRef,
    VisualWorkerRequest,
)
from backend.app.extraction.visual.renderer import RenderLimits, render_page
from backend.app.extraction.visual.result_store import (
    cleanup_staging,
    delete_results,
    load_page,
    load_summary,
    publish_page_atomic,
    publish_summary_atomic,
)
from backend.app.extraction.visual.visibility import VisibilityThresholds, probe_native_visibility
from backend.app.extraction.visual.worker_manager import OcrWorkerManager
from backend.app.processing.cancellation import CancellationToken
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
    if unique == {SourceMode.IMAGE_AUTHORITY} or (
        image_origin_document and SourceMode.NATIVE_AUTHORITY not in unique
    ):
        return DocumentSourcePolicy.IMAGE_AUTHORITY
    if unique == {SourceMode.VISUAL_AUTHORITY}:
        return DocumentSourcePolicy.VISUAL_AUTHORITY
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

    def suppress_native_page_text(self, page: NativePageResult) -> NativePageResult:
        """Remove public native words/chars after visibility downgrade."""

        trust = page.trust.model_copy(
            update={
                "visual_agreement_status": VisualAgreementStatus.EVALUATED_PHASE_4_VISIBILITY,
                "visual_processing_required": True,
                "native_result_available": False,
                "source_mode": SourceMode.VISUAL_AUTHORITY,
                "decision": NativePageDecision.REJECTED,
                "reason_codes": list(
                    dict.fromkeys(
                        [
                            *page.trust.reason_codes,
                            "native_text_not_visually_present",
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
        visibility_by_page: dict[int, NativeVisibilityResult] = {}
        published: dict[int, VisualPageResult] = {}

        async def _progress(payload: dict[str, Any]) -> None:
            if on_progress is not None:
                result = on_progress(payload)
                if inspect.isawaitable(result):
                    await result

        # Visibility probes for accepted natives.
        for page_number, native_page in sorted(native_pages.items()):
            if cancel_token is not None:
                cancel_token.raise_if_cancelled()
            probe_enabled = self._settings.native_visibility_probe_enabled
            if page_needs_visibility_probe(native_page) and probe_enabled:
                await _progress(
                    {
                        "type": "native_visibility_started",
                        "page_number": page_number,
                    }
                )
                meta = page_by_number[page_number]
                limits = RenderLimits(
                    target_dpi=float(self._settings.ocr_visibility_probe_dpi),
                    min_effective_dpi=float(self._settings.ocr_visibility_probe_dpi),
                    max_render_pixels=self._settings.ocr_max_render_pixels,
                    max_render_side_pixels=self._settings.ocr_max_render_side_pixels,
                    dimension_tolerance_points=self._settings.canonical_page_dimension_tolerance_points,
                )
                rendered = render_page(
                    canonical_pdf,
                    page_number=page_number,
                    page_width_points=meta.width_points,
                    page_height_points=meta.height_points,
                    limits=limits,
                )
                try:
                    vis = probe_native_visibility(
                        rendered.image,
                        native_page,
                        thresholds=VisibilityThresholds(
                            min_words=self._settings.native_visibility_min_words,
                            min_visible_word_ratio=self._settings.native_visibility_min_visible_word_ratio,
                            min_region_variance=self._settings.native_visibility_min_region_variance,
                            min_edge_density=self._settings.native_visibility_min_edge_density,
                        ),
                    )
                finally:
                    rendered.image.close()
                visibility_by_page[page_number] = vis
                if vis.downgraded:
                    downgraded.add(page_number)
                    native_pages[page_number] = self.suppress_native_page_text(native_page)
                    selected.append(page_number)
                    await _progress(
                        {
                            "type": "native_visibility_rejected",
                            "page_number": page_number,
                            "reason_codes": vis.reason_codes,
                        }
                    )
                else:
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
                    await _progress(
                        {
                            "type": "native_visibility_supported",
                            "page_number": page_number,
                        }
                    )
            elif page_requires_visual(native_page):
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

        selected = sorted(set(selected))
        await _progress(
            {
                "type": "visual_pages_selected",
                "pages_selected": len(selected),
                "pages_total": len(canonical_pages),
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
            request = VisualWorkerRequest(
                request_id=job_id,
                session_id=session_id,
                document_id=document_id,
                job_id=job_id,
                canonical_pdf_path=str(canonical_pdf),
                pages=page_refs,
                page_output_dir=str(results),
                staging_dir=str(staging),
                config=config,
            )

            async def _worker_progress(payload: dict[str, Any]) -> None:
                await _progress(payload)

            with contextlib.suppress(VisualOcrError):
                # Preserve any pages already published on worker failure.
                await self._worker.process_document(
                    request,
                    cancel_token=cancel_token,
                    on_progress=_worker_progress,
                )

            for n in selected:
                page_result = load_page(results, n)
                if page_result is not None:
                    if n in visibility_by_page and page_result.native_visibility_result is None:
                        page_result = page_result.model_copy(
                            update={"native_visibility_result": visibility_by_page[n]}
                        )
                        publish_page_atomic(page_result, results)
                    published[n] = page_result

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

        if not selected:
            status = VisualProcessingStatus.NOT_REQUIRED
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
        summary = VisualDocumentSummary(
            document_id=document_id,
            visual_processing_status=status,
            page_count=len(canonical_pages),
            pages_selected=len(selected),
            pages_completed=completed + no_text,
            pages_no_text=no_text,
            pages_failed=failed,
            pages_cancelled=cancelled,
            native_pages_retained=len(retained_native),
            native_pages_downgraded=len(downgraded),
            visual_result_available=visual_available,
            handwriting_assessment_pending=True,
            final_result_available=False,
            document_source_policy=policy,
            progress=VisualProgress(
                percent=65,
                pages_completed=completed + no_text + len(retained_native),
                pages_total=len(canonical_pages),
            ),
            model_info=model_info,
            page_summaries=summaries,
            warnings=[],
            created_at=created_at,
            completed_at=datetime.now(UTC),
            user_status_message=_PHASE4_USER_MESSAGE,
        )
        publish_summary_atomic(summary, results)
        cleanup_staging(staging)
        return summary
