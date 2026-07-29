"""End-to-end targeted-repair pipeline with staging and cleanup."""

from __future__ import annotations

import logging
import shutil
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.contracts.native import NativeWord, SourceMode
from backend.app.contracts.ocr import HandwritingAssessment
from backend.app.contracts.repair import (
    BaseSourceMode,
    RepairMethod,
    RepairQualityStatus,
    RepairRegionRecord,
    TargetedRepairEligibilityEvidence,
    TargetedRepairPageSummary,
)
from backend.app.contracts.routing import RepairRegionDiagnostics
from backend.app.contracts.visual import (
    AgreementEvaluationStatus,
    OverlaySourceKind,
    PageResultState,
    VisualPageResult,
    VisualPageStatus,
    VisualWarning,
    source_label_for_page_result_state,
)
from backend.app.extraction.routing.models import RoutingPolicy
from backend.app.extraction.routing.repair_clustering import cluster_failed_boxes
from backend.app.extraction.routing.repair_eligibility import evaluate_targeted_repair_eligibility
from backend.app.extraction.routing.repair_methods import (
    DetectRecogniseFn,
    RecogniseCropFn,
    execute_regions,
)
from backend.app.extraction.routing.repair_quality import evaluate_repair_quality
from backend.app.extraction.routing.repair_reconcile import (
    classify_base_words,
    reconcile_repaired_page,
)
from backend.app.extraction.visual.result_store import publish_page_atomic
from backend.app.processing.cancellation import CancellationToken, JobCancelledError
from PIL import Image

logger = logging.getLogger("veridemand.routing.repair_pipeline")

ProgressFn = Callable[[dict[str, Any]], Awaitable[None] | None]


@dataclass(slots=True)
class TargetedRepairPipelineResult:
    """Outcome of one page repair attempt."""

    eligibility: TargetedRepairEligibilityEvidence
    regions: list[RepairRegionRecord] = field(default_factory=list)
    page_result: VisualPageResult | None = None
    quality_status: RepairQualityStatus | None = None
    fallback_to_full_ocr: bool = False
    summary: TargetedRepairPageSummary | None = None
    diagnostics: list[RepairRegionDiagnostics] = field(default_factory=list)
    duration_ms: int = 0
    peak_rss_bytes: int | None = None


def repair_staging_dir(base_staging: Path, page_number: int) -> Path:
    return base_staging / "targeted_repair" / f"page-{page_number:04d}"


def cleanup_repair_staging(path: Path) -> None:
    """Remove repair crops and temporary outputs; never log contents."""

    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def cleanup_all_repair_staging(base_staging: Path) -> None:
    root = base_staging / "targeted_repair"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)


async def _emit(progress: ProgressFn | None, payload: dict[str, Any]) -> None:
    if progress is None:
        return
    result = progress(payload)
    if result is not None:
        await result


def _peak_rss() -> int | None:
    try:
        import psutil

        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


async def run_targeted_repair_pipeline(
    *,
    page_number: int,
    words: Sequence[NativeWord],
    failed_indices: Sequence[int],
    page_image: Image.Image,
    policy: RoutingPolicy,
    visual_agreement_score: float | None,
    recognition_agreement_score: float | None,
    page_width_points: float,
    page_height_points: float,
    render_scale: float,
    intrinsic_rotation: int,
    recognise_crop: RecogniseCropFn,
    detect_recognise: DetectRecogniseFn,
    results_dir: Path,
    staging_dir: Path,
    cancel_token: CancellationToken | None = None,
    on_progress: ProgressFn | None = None,
    geometry_shifted: bool = False,
    route_reason_codes: Sequence[str] | None = None,
    document_id: str | None = None,
) -> TargetedRepairPipelineResult:
    """Cluster, repair, quality-gate, reconcile, and atomically publish — or fall back."""

    started = time.perf_counter()
    staging = repair_staging_dir(staging_dir, page_number)
    staging.mkdir(parents=True, exist_ok=True)
    peak = _peak_rss()

    def _check_cancel() -> None:
        if cancel_token is not None:
            cancel_token.raise_if_cancelled()

    try:
        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_region_clustering",
                "page_number": page_number,
                "status": "started",
            },
        )
        _check_cancel()
        default_method = (
            RepairMethod.LOCAL_DETECTION_AND_RECOGNITION
            if geometry_shifted
            else RepairMethod.RECOGNITION_ONLY
        )
        regions = cluster_failed_boxes(
            words,
            failed_indices,
            page_number=page_number,
            policy=policy,
            failure_reason_codes=list(route_reason_codes or ["verification_failed"]),
            default_method=default_method,
        )
        eligibility = evaluate_targeted_repair_eligibility(
            page_number=page_number,
            words=words,
            failed_indices=failed_indices,
            regions=regions,
            policy=policy,
            visual_agreement_score=visual_agreement_score,
            recognition_agreement_score=recognition_agreement_score,
            base_source_mode=BaseSourceMode.VERIFIED_EMBEDDED,
            geometry_shifted=geometry_shifted,
        )
        logger.info(
            "targeted_repair_decision",
            extra={
                "document_id": document_id,
                "page_number": page_number,
                "base_source_mode": eligibility.base_source_mode.value,
                "failed_word_count": eligibility.failed_word_count,
                "failed_region_count": eligibility.failed_region_count,
                "failed_region_coverage_ratio": eligibility.failed_region_coverage_ratio,
                "repair_eligible": eligibility.repair_eligible,
                "repair_method": eligibility.repair_method.value
                if eligibility.repair_method
                else None,
                "repair_reason_codes": list(eligibility.repair_reason_codes),
            },
        )
        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_region_clustering",
                "page_number": page_number,
                "status": "completed",
                "failed_region_count": len(regions),
            },
        )

        if not eligibility.repair_eligible:
            cleanup_repair_staging(staging)
            return TargetedRepairPipelineResult(
                eligibility=eligibility,
                regions=regions,
                fallback_to_full_ocr=True,
                quality_status=RepairQualityStatus.REPAIR_INSUFFICIENT,
                duration_ms=int((time.perf_counter() - started) * 1000),
                peak_rss_bytes=peak,
            )

        assert eligibility.repair_method is not None
        method = eligibility.repair_method
        # Stamp method onto regions.
        regions = [r.model_copy(update={"repair_method": method}) for r in regions]

        region_total = len(regions)
        await _emit(
            on_progress,
            {
                "type": "targeted_repair_progress",
                "page_number": page_number,
                "repair_region_index": 0,
                "repair_regions_total": region_total,
                "repair_method": method.value,
                "regions_completed": 0,
                "regions_remaining": region_total,
            },
        )

        all_candidates = []
        diagnostics: list[RepairRegionDiagnostics] = []
        for idx, region in enumerate(regions):
            _check_cancel()
            op = (
                "targeted_repair_recognition"
                if method is RepairMethod.RECOGNITION_ONLY
                else "targeted_repair_local_detection"
            )
            await _emit(
                on_progress,
                {
                    "type": "operation",
                    "operation": "targeted_repair_crop",
                    "page_number": page_number,
                    "repair_region_index": idx + 1,
                    "repair_regions_total": region_total,
                    "status": "started",
                },
            )
            await _emit(
                on_progress,
                {
                    "type": "operation",
                    "operation": op,
                    "page_number": page_number,
                    "repair_region_index": idx + 1,
                    "repair_regions_total": region_total,
                    "status": "started",
                },
            )
            outcomes = execute_regions(
                page_image,
                words,
                [region],
                policy,
                method=method,
                page_width_points=page_width_points,
                page_height_points=page_height_points,
                render_scale=render_scale,
                intrinsic_rotation=intrinsic_rotation,
                recognise_crop=recognise_crop,
                detect_recognise=detect_recognise,
            )
            outcome = outcomes[0]
            all_candidates.extend(outcome.candidates)
            d = outcome.diagnostics
            diagnostics.append(
                RepairRegionDiagnostics(
                    repair_region_id=d.repair_region_id,
                    page_number=d.page_number,
                    repair_method=d.method.value,
                    source_box_count=len(region.source_word_ids),
                    crop_width=d.crop_width,
                    crop_height=d.crop_height,
                    recognition_count=d.result_count,
                    duration_ms=d.duration_ms,
                    replacement_count=d.result_count,
                    reason_codes=list(d.reason_codes),
                )
            )
            await _emit(
                on_progress,
                {
                    "type": "operation",
                    "operation": op,
                    "page_number": page_number,
                    "repair_region_index": idx + 1,
                    "repair_regions_total": region_total,
                    "status": "completed",
                },
            )
            await _emit(
                on_progress,
                {
                    "type": "targeted_repair_progress",
                    "page_number": page_number,
                    "repair_region_index": idx + 1,
                    "repair_regions_total": region_total,
                    "repair_method": method.value,
                    "regions_completed": idx + 1,
                    "regions_remaining": region_total - (idx + 1),
                },
            )

        # Optional one-shot method transition when recognition-only is empty.
        if (
            not all_candidates
            and method is RepairMethod.RECOGNITION_ONLY
            and policy.allow_repair_method_transition
        ):
            method = RepairMethod.LOCAL_DETECTION_AND_RECOGNITION
            all_candidates = []
            diagnostics = []
            for _idx, region in enumerate(regions):
                _check_cancel()
                outcomes = execute_regions(
                    page_image,
                    words,
                    [region],
                    policy,
                    method=method,
                    page_width_points=page_width_points,
                    page_height_points=page_height_points,
                    render_scale=render_scale,
                    intrinsic_rotation=intrinsic_rotation,
                    recognise_crop=recognise_crop,
                    detect_recognise=detect_recognise,
                )
                outcome = outcomes[0]
                all_candidates.extend(outcome.candidates)
                d = outcome.diagnostics
                diagnostics.append(
                    RepairRegionDiagnostics(
                        repair_region_id=d.repair_region_id,
                        page_number=d.page_number,
                        repair_method=d.method.value,
                        source_box_count=len(region.source_word_ids),
                        crop_width=d.crop_width,
                        crop_height=d.crop_height,
                        recognition_count=d.result_count,
                        duration_ms=d.duration_ms,
                        replacement_count=d.result_count,
                        reason_codes=[*d.reason_codes, "method_transition_local_detection"],
                    )
                )

        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_quality_evaluation",
                "page_number": page_number,
                "status": "started",
            },
        )
        quality = evaluate_repair_quality(
            page_number=page_number,
            regions=regions,
            repaired=all_candidates,
            policy=policy,
            expected_failed_word_count=len(failed_indices),
        )
        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_quality_evaluation",
                "page_number": page_number,
                "status": "completed",
                "repair_quality_status": quality.status.value,
            },
        )

        if quality.fallback_to_full_ocr:
            cleanup_repair_staging(staging)
            logger.info(
                "targeted_repair_decision",
                extra={
                    "document_id": document_id,
                    "page_number": page_number,
                    "repair_quality_status": quality.status.value,
                    "fallback_to_full_ocr": True,
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                    "peak_rss_bytes": _peak_rss(),
                },
            )
            await _emit(
                on_progress,
                {
                    "type": "embedded_ocr_targeted_repair_insufficient",
                    "page_number": page_number,
                    "repair_quality_status": quality.status.value,
                    "reason_codes": list(quality.reason_codes),
                },
            )
            return TargetedRepairPipelineResult(
                eligibility=eligibility,
                regions=regions,
                quality_status=quality.status,
                fallback_to_full_ocr=True,
                diagnostics=diagnostics,
                duration_ms=int((time.perf_counter() - started) * 1000),
                peak_rss_bytes=_peak_rss(),
            )

        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_reconciliation",
                "page_number": page_number,
                "status": "started",
            },
        )
        classified = classify_base_words(words, failed_indices=failed_indices, regions=regions)
        reconciled = reconcile_repaired_page(
            page_number=page_number,
            classified=classified,
            repaired=all_candidates,
            regions=regions,
            width_px=page_image.width,
            height_px=page_image.height,
            agreement_score=visual_agreement_score or 0.85,
        )
        reconciled.summary.repair_quality_status = quality.status
        reconciled.summary.repair_method = method
        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_reconciliation",
                "page_number": page_number,
                "status": "completed",
                "retained_word_count": reconciled.summary.retained_embedded_words,
                "repaired_word_count": reconciled.summary.repaired_words,
                "suppressed_word_count": reconciled.summary.suppressed_words,
            },
        )

        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_publication",
                "page_number": page_number,
                "status": "started",
            },
        )
        page_result = VisualPageResult(
            page_number=page_number,
            status=VisualPageStatus.TARGETED_REPAIR_COMPLETED,
            source_mode=SourceMode.EMBEDDED_OCR_AUTHORITY,
            page_result_state=PageResultState.EMBEDDED_OCR_TARGETED_REPAIR,
            source_label=source_label_for_page_result_state(
                PageResultState.EMBEDDED_OCR_TARGETED_REPAIR
            ),
            render_width_pixels=page_image.width,
            render_height_pixels=page_image.height,
            line_count=len(reconciled.lines),
            word_count=len(reconciled.words),
            lines=reconciled.lines,
            words=reconciled.words,
            average_recognition_score=(
                sum(w.recognition_score for w in reconciled.words) / len(reconciled.words)
                if reconciled.words
                else None
            ),
            page_route=PageResultState.EMBEDDED_OCR_TARGETED_REPAIR.value,
            route_reason_codes=list(route_reason_codes or eligibility.repair_reason_codes),
            visual_agreement_status=AgreementEvaluationStatus.PASSED,
            visual_agreement_score=visual_agreement_score,
            visual_agreement_policy_version=policy.version,
            recognition_agreement_status=(
                AgreementEvaluationStatus.PASSED
                if recognition_agreement_score is not None
                and recognition_agreement_score >= policy.min_recognition_agreement
                else AgreementEvaluationStatus.NOT_REQUIRED
                if recognition_agreement_score is None
                else AgreementEvaluationStatus.FAILED
            ),
            recognition_agreement_score=recognition_agreement_score,
            overlay_source=OverlaySourceKind.TARGETED_REPAIR_WORD,
            visual_result_available=True,
            visual_processing_attempted=True,
            handwriting_assessment=HandwritingAssessment.PENDING_PHASE_5,
            retained_native_words=reconciled.summary.retained_native_words,
            retained_embedded_words=reconciled.summary.retained_embedded_words,
            repaired_words=reconciled.summary.repaired_words,
            suppressed_words=reconciled.summary.suppressed_words,
            repair_region_count=reconciled.summary.repair_regions,
            repair_quality_status=quality.status.value,
            repair_method=method.value,
            duration_ms=int((time.perf_counter() - started) * 1000),
            warnings=[
                VisualWarning(
                    code="targeted_repair_completed",
                    message="Verified embedded OCR with bounded visual repair.",
                    page_number=page_number,
                )
            ]
            if quality.status is RepairQualityStatus.REPAIR_COMPLETE
            else [
                VisualWarning(
                    code="targeted_repair_warnings",
                    message="Targeted repair completed with quality warnings.",
                    page_number=page_number,
                )
            ],
        )
        publish_page_atomic(page_result, results_dir)
        await _emit(
            on_progress,
            {
                "type": "operation",
                "operation": "targeted_repair_publication",
                "page_number": page_number,
                "status": "completed",
            },
        )
        await _emit(
            on_progress,
            {
                "type": "embedded_ocr_targeted_repair_completed",
                "page_number": page_number,
                "retained_word_count": reconciled.summary.retained_embedded_words,
                "repaired_word_count": reconciled.summary.repaired_words,
                "suppressed_word_count": reconciled.summary.suppressed_words,
                "repair_regions": reconciled.summary.repair_regions,
                "repair_quality_status": quality.status.value,
            },
        )
        logger.info(
            "targeted_repair_decision",
            extra={
                "document_id": document_id,
                "page_number": page_number,
                "regions_completed": len(regions),
                "retained_word_count": reconciled.summary.retained_embedded_words,
                "repaired_word_count": reconciled.summary.repaired_words,
                "suppressed_word_count": reconciled.summary.suppressed_words,
                "repair_quality_status": quality.status.value,
                "fallback_to_full_ocr": False,
                "duration_ms": page_result.duration_ms,
                "peak_rss_bytes": _peak_rss(),
            },
        )
        cleanup_repair_staging(staging)
        return TargetedRepairPipelineResult(
            eligibility=eligibility,
            regions=regions,
            page_result=page_result,
            quality_status=quality.status,
            fallback_to_full_ocr=False,
            summary=reconciled.summary,
            diagnostics=diagnostics,
            duration_ms=int((time.perf_counter() - started) * 1000),
            peak_rss_bytes=_peak_rss(),
        )
    except JobCancelledError:
        cleanup_repair_staging(staging)
        cleanup_all_repair_staging(staging_dir)
        raise
    except Exception:
        cleanup_repair_staging(staging)
        raise
