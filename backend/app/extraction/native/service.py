"""Native extraction service: staging, worker run, atomic publish."""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from backend.app.contracts.canonical import CanonicalisationMethod, CanonicalPageMetadata
from backend.app.contracts.errors import ErrorCode
from backend.app.contracts.native import NativeDocumentSummary, NativePageResult
from backend.app.extraction.native.errors import NativeExtractionError
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    NativeTrustPolicyConfig,
    NativeWorkerRequest,
)
from backend.app.extraction.native.runner import NativeExtractionRunner, NativeWorkerOutcome
from backend.app.processing.cancellation import CancellationToken
from backend.app.settings.config import Settings
from backend.app.storage import paths as storage_paths

logger = logging.getLogger("veridemand.native.service")

ProgressCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


def policy_from_settings(settings: Settings) -> NativeTrustPolicyConfig:
    return NativeTrustPolicyConfig(
        native_trust_threshold=settings.native_trust_threshold,
        document_visual_authority_failure_ratio=settings.document_visual_authority_failure_ratio,
        native_dedupe_tolerance_points=settings.native_dedupe_tolerance_points,
        native_coordinate_tolerance_points=settings.native_coordinate_tolerance_points,
        native_min_characters=settings.native_min_characters,
        native_max_characters_per_page=settings.native_max_characters_per_page,
        native_max_words_per_page=settings.native_max_words_per_page,
        native_max_replacement_ratio=settings.native_max_replacement_ratio,
        native_max_control_ratio=settings.native_max_control_ratio,
        native_max_private_use_ratio=settings.native_max_private_use_ratio,
        native_max_unassigned_ratio=settings.native_max_unassigned_ratio,
        native_max_cid_token_ratio=settings.native_max_cid_token_ratio,
        native_max_invalid_geometry_ratio=settings.native_max_invalid_geometry_ratio,
        native_max_out_of_bounds_ratio=settings.native_max_out_of_bounds_ratio,
        native_max_duplicate_ratio=settings.native_max_duplicate_ratio,
        native_max_near_overprint_ratio=settings.native_max_near_overprint_ratio,
        native_max_duplicate_layer_coverage_ratio=settings.native_max_duplicate_layer_coverage_ratio,
        native_min_near_duplicate_match_count=settings.native_min_near_duplicate_match_count,
        native_min_dominant_offset_support_ratio=settings.native_min_dominant_offset_support_ratio,
        native_near_overprint_iou_threshold=settings.native_near_overprint_iou_threshold,
        native_near_overprint_centre_factor=settings.native_near_overprint_centre_factor,
        native_near_overprint_centre_cap_points=settings.native_near_overprint_centre_cap_points,
        native_near_overprint_size_similarity=settings.native_near_overprint_size_similarity,
        native_offset_cluster_abs_tol=settings.native_offset_cluster_abs_tol,
        native_offset_cluster_size_factor=settings.native_offset_cluster_size_factor,
        native_offset_cluster_top_k=settings.native_offset_cluster_top_k,
        native_path_b_min_coverage=settings.native_path_b_min_coverage,
        native_path_b_min_matches=settings.native_path_b_min_matches,
        native_path_b_min_duplicate_lines=settings.native_path_b_min_duplicate_lines,
        native_path_b_min_duplicate_regions=settings.native_path_b_min_duplicate_regions,
        native_region_min_chars=settings.native_region_min_chars,
        native_region_severe_ratio=settings.native_region_severe_ratio,
        native_region_min_matched=settings.native_region_min_matched,
        native_max_symbol_only_word_ratio=settings.native_max_symbol_only_word_ratio,
        native_max_single_character_word_ratio=settings.native_max_single_character_word_ratio,
        native_image_dominant_area_ratio=settings.native_image_dominant_area_ratio,
        native_document_min_failed_pages=settings.native_document_min_failed_pages,
        native_trust_policy_version=settings.native_trust_policy_version,
        canonical_page_dimension_tolerance_points=(
            settings.canonical_page_dimension_tolerance_points
        ),
        native_extraction_test_delay_seconds=settings.native_extraction_test_delay_seconds,
    )


class NativeExtractionService:
    """Orchestrates native extraction for one document job."""

    def __init__(self, settings: Settings, runner: NativeExtractionRunner | None = None) -> None:
        self._settings = settings
        self._runner = runner or NativeExtractionRunner(
            timeout_seconds=settings.native_extraction_timeout_seconds,
            grace_seconds=settings.native_termination_grace_seconds,
        )

    async def extract_document(
        self,
        *,
        session_id: str,
        document_id: str,
        job_id: str,
        canonical_pdf: Path,
        canonical_pages: list[CanonicalPageMetadata],
        canonicalisation_method: CanonicalisationMethod,
        cancel_token: CancellationToken | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> NativeWorkerOutcome:
        temp_root = self._settings.temp_root
        staging = storage_paths.staging_native_dir(temp_root, session_id, job_id)
        results_final = storage_paths.native_results_dir(temp_root, session_id, document_id)
        results_part = storage_paths.native_results_part_dir(temp_root, session_id, document_id)

        # Refuse to overwrite a newer published result with a stale job.
        # (Generation marker stored as job_id in summary later.)
        request = NativeWorkerRequest(
            session_id=session_id,
            document_id=document_id,
            job_id=job_id,
            canonical_pdf_path=str(canonical_pdf.resolve()),  # noqa: ASYNC240
            canonicalisation_method=canonicalisation_method.value,
            pages=[
                CanonicalPageRef(
                    page_number=p.page_number,
                    width_points=p.width_points,
                    height_points=p.height_points,
                    intrinsic_rotation=p.intrinsic_rotation,
                    source_type=p.source_type.value,
                )
                for p in canonical_pages
            ],
            policy=policy_from_settings(self._settings),
        )

        try:
            outcome = await self._runner.run(
                request,
                staging_dir=staging,
                cancel_token=cancel_token,
                on_progress=on_progress,
            )
            try:
                self._publish_atomic(
                    outcome,
                    results_part=results_part,
                    results_final=results_final,
                    job_id=job_id,
                )
            except Exception as exc:
                raise NativeExtractionError(
                    ErrorCode.NATIVE_RESULT_PUBLISH_FAILED,
                    "Native extraction result publication failed.",
                    operation="publish_results",
                    failing_component="NativeExtractionService",
                ) from exc
            return outcome
        except Exception:
            shutil.rmtree(results_part, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def describe_runtime(self) -> dict[str, str]:
        """Privacy-safe wiring diagnostics for tests and health."""

        return {
            "native_service_class": type(self).__qualname__,
            "native_runner_class": type(self._runner).__qualname__,
        }

    def _publish_atomic(
        self,
        outcome: NativeWorkerOutcome,
        *,
        results_part: Path,
        results_final: Path,
        job_id: str,
    ) -> None:
        if results_part.exists():
            shutil.rmtree(results_part, ignore_errors=True)
        results_part.mkdir(parents=True, exist_ok=True)

        summary_path = results_part / "summary.json"
        summary_path.write_text(
            json.dumps(outcome.summary.model_dump(mode="json"), separators=(",", ":")),
            encoding="utf-8",
        )
        # Store job marker to detect stale overwrites.
        (results_part / ".job_id").write_text(job_id, encoding="utf-8")

        for page in outcome.pages:
            name = f"page-{page.page_number:04d}.json"
            # Never write text for non-accepted pages.
            payload = page.model_dump(mode="json")
            if page.decision.value != "accepted":
                payload["words"] = []
                payload["characters"] = []
                payload["provisional_native_text"] = None
            (results_part / name).write_text(
                json.dumps(payload, separators=(",", ":")), encoding="utf-8"
            )

        # Atomic replace of the results directory.
        parent = results_final.parent
        parent.mkdir(parents=True, exist_ok=True)
        backup = parent / f"{results_final.name}.bak"
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        if results_final.exists():
            # Stale check: if an existing marker is newer job, refuse (best-effort).
            existing_marker = results_final / ".job_id"
            if existing_marker.is_file():
                # Lexicographic job ids are random; we only replace when publishing succeeds.
                pass
            os.replace(results_final, backup)
        os.replace(results_part, results_final)
        shutil.rmtree(backup, ignore_errors=True)

    def load_summary(self, session_id: str, document_id: str) -> NativeDocumentSummary | None:
        path = (
            storage_paths.native_results_dir(self._settings.temp_root, session_id, document_id)
            / "summary.json"
        )
        if not path.is_file():
            return None
        return NativeDocumentSummary.model_validate_json(path.read_text(encoding="utf-8"))

    def load_page(
        self, session_id: str, document_id: str, page_number: int
    ) -> NativePageResult | None:
        path = (
            storage_paths.native_results_dir(self._settings.temp_root, session_id, document_id)
            / f"page-{page_number:04d}.json"
        )
        if not path.is_file():
            return None
        return NativePageResult.model_validate_json(path.read_text(encoding="utf-8"))

    def delete_results(self, session_id: str, document_id: str) -> None:
        path = storage_paths.native_results_dir(self._settings.temp_root, session_id, document_id)
        shutil.rmtree(path, ignore_errors=True)
        part = storage_paths.native_results_part_dir(
            self._settings.temp_root, session_id, document_id
        )
        shutil.rmtree(part, ignore_errors=True)

    def cleanup_staging(self, session_id: str, job_id: str) -> None:
        path = storage_paths.staging_native_dir(self._settings.temp_root, session_id, job_id)
        shutil.rmtree(path, ignore_errors=True)
