"""Orchestrate page-by-page and whole-document smoke corpus runs."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx

from scripts.smoke_corpus import CRITICAL_SUBSET, PHASE4_SUBSET
from scripts.smoke_corpus.assert_page import assert_page
from scripts.smoke_corpus.client import (
    canonical_page_meta,
    delete_session,
    document_escalated,
    process_pdf,
    trust_for_page,
)
from scripts.smoke_corpus.report import PageResultRow, SmokeReport
from scripts.smoke_corpus.split import split_page_to_pdf
from scripts.smoke_corpus.validate import CorpusBundle, validate_corpus


def filter_pages(
    pages: Sequence[dict[str, Any]],
    *,
    start_page: int | None = None,
    end_page: int | None = None,
    test_ids: Sequence[str] | None = None,
    critical_subset: bool = False,
    phase4_subset: bool = False,
) -> list[dict[str, Any]]:
    selected = list(pages)
    if critical_subset:
        wanted = set(CRITICAL_SUBSET)
        selected = [p for p in selected if p.get("test_id") in wanted]
    if phase4_subset:
        wanted = set(PHASE4_SUBSET)
        selected = [p for p in selected if p.get("test_id") in wanted]
    if test_ids:
        wanted = {t.strip() for t in test_ids if t.strip()}
        selected = [p for p in selected if p.get("test_id") in wanted]
    if start_page is not None:
        selected = [p for p in selected if int(p.get("page_number") or 0) >= start_page]
    if end_page is not None:
        selected = [p for p in selected if int(p.get("page_number") or 0) <= end_page]
    return selected


def _error_detail(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTPStatusError:{exc.response.status_code}"
    return type(exc).__name__


async def _process_one_page(
    client: httpx.AsyncClient,
    *,
    temp_pdf: Path,
    test_id: str,
    manifest_page: dict[str, Any],
) -> tuple[str, dict[str, Any] | None, list[str], list[str], str]:
    """Return status, trust, failure_codes, notes, session_id."""

    last_exc: BaseException | None = None
    for attempt in range(3):
        session_id: str | None = None
        try:
            processed = await process_pdf(
                client,
                temp_pdf,
                filename=f"{test_id}.pdf",
                fetch_pages=[1],
                include_characters=False,
                collect_sse=False,
            )
            session_id = processed.session_id
            trust = trust_for_page(processed.summary, 1)
            page_result = processed.page_results.get(1)
            visual_page = processed.visual_page_results.get(1)
            canonical_page = canonical_page_meta(processed.canonical_metadata, 1)
            escalated = document_escalated(processed.summary)
            assertion = assert_page(
                manifest_page=manifest_page,
                trust=trust,
                page_result=page_result,
                canonical_page=canonical_page,
                canonical_ok=processed.canonical_ok,
                document_escalated=escalated,
                sse_blobs=processed.sse_blobs,
                public_file_blobs=processed.public_result_blobs,
                visual_page=visual_page,
                visual_summary=processed.visual_summary,
                document_status=str(processed.document.get("status") or ""),
            )
            return (
                assertion.status,
                trust,
                [f.code for f in assertion.failures],
                list(assertion.notes),
                session_id,
            )
        except Exception as exc:
            last_exc = exc
            if session_id is not None:
                await delete_session(client, session_id)
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            raise
    assert last_exc is not None
    raise last_exc


async def run_page_by_page(
    *,
    api_base_url: str,
    bundle: CorpusBundle,
    pages: Sequence[dict[str, Any]],
    fail_fast: bool = False,
    keep_temporary_files: bool = False,
) -> SmokeReport:
    version = str(bundle.manifest.get("version") or "unknown")
    report = SmokeReport(corpus_version=version, mode="page-by-page")
    temp_root = Path(tempfile.mkdtemp(prefix="veridemand-smoke-"))
    try:
        async with httpx.AsyncClient(base_url=api_base_url, timeout=120.0) as client:
            for page in pages:
                test_id = str(page.get("test_id"))
                page_number = int(page["page_number"])
                temp_pdf = temp_root / f"{test_id}-page-{page_number:04d}.pdf"
                split_page_to_pdf(bundle.pdf_path, page_number, temp_pdf)

                session_id: str | None = None
                try:
                    status, trust, failure_codes, notes, session_id = await _process_one_page(
                        client,
                        temp_pdf=temp_pdf,
                        test_id=test_id,
                        manifest_page=page,
                    )
                    report.add(
                        PageResultRow(
                            test_id=test_id,
                            page_number=page_number,
                            status=status,  # type: ignore[arg-type]
                            actual_authority=(str(trust.get("source_mode")) if trust else None),
                            actual_decision=str(trust.get("decision")) if trust else None,
                            reason_codes=(
                                [str(c) for c in (trust.get("reason_codes") or [])] if trust else []
                            ),
                            failure_codes=failure_codes,
                            notes=notes,
                        )
                    )
                    if status == "failed" and fail_fast:
                        break
                except Exception as exc:
                    report.add(
                        PageResultRow(
                            test_id=test_id,
                            page_number=page_number,
                            status="failed",
                            failure_codes=["runner_error"],
                            notes=[f"{_error_detail(exc)}: details suppressed"],
                        )
                    )
                    if fail_fast:
                        break
                finally:
                    if session_id is not None:
                        await delete_session(client, session_id)
                    if not keep_temporary_files and temp_pdf.exists():
                        temp_pdf.unlink(missing_ok=True)
    finally:
        if not keep_temporary_files:
            shutil.rmtree(temp_root, ignore_errors=True)
    return report


async def run_whole_document(
    *,
    api_base_url: str,
    bundle: CorpusBundle,
    pages: Sequence[dict[str, Any]],
    fail_fast: bool = False,
) -> SmokeReport:
    version = str(bundle.manifest.get("version") or "unknown")
    report = SmokeReport(corpus_version=version, mode="whole-document")

    async with httpx.AsyncClient(base_url=api_base_url, timeout=300.0) as client:
        session_id: str | None = None
        try:
            processed = await process_pdf(
                client,
                bundle.pdf_path,
                filename=bundle.pdf_path.name,
                fetch_pages=[],
                include_characters=False,
                collect_sse=False,
            )
            session_id = processed.session_id

            if processed.document.get("status") not in {
                "native_trust_complete",
                "failed",
            }:
                report.add(
                    PageResultRow(
                        test_id="DOCUMENT",
                        page_number=0,
                        status="failed",
                        failure_codes=["unexpected_status"],
                        notes=[f"status={processed.document.get('status')!r}"],
                    )
                )
                return report

            if not processed.canonical_ok:
                report.add(
                    PageResultRow(
                        test_id="DOCUMENT",
                        page_number=0,
                        status="failed",
                        failure_codes=["canonical_not_viewable"],
                    )
                )
                return report

            summary = processed.summary or {}
            page_count = int(summary.get("page_count") or 0)
            expected = int(bundle.manifest.get("page_count_including_cover") or 0)
            if page_count != expected:
                report.add(
                    PageResultRow(
                        test_id="DOCUMENT",
                        page_number=0,
                        status="failed",
                        failure_codes=["canonical_page_count_mismatch"],
                        notes=[f"actual={page_count} expected={expected}"],
                    )
                )
                return report

            escalated = document_escalated(summary)
            decisions = {
                int(d["page_number"]): d
                for d in (summary.get("page_decisions") or [])
                if isinstance(d, dict) and "page_number" in d
            }

            if 1 not in decisions and page_count >= 1:
                report.add(
                    PageResultRow(
                        test_id="COVER",
                        page_number=1,
                        status="failed",
                        failure_codes=["cover_decision_missing"],
                    )
                )
                if fail_fast:
                    return report

            for page in pages:
                test_id = str(page.get("test_id"))
                page_number = int(page["page_number"])
                trust = decisions.get(page_number)
                canonical_page = canonical_page_meta(processed.canonical_metadata, page_number)
                assertion = assert_page(
                    manifest_page=page,
                    trust=trust,
                    page_result=None,
                    canonical_page=canonical_page,
                    canonical_ok=processed.canonical_ok,
                    document_escalated=escalated,
                )
                status = assertion.status
                if (
                    escalated
                    and trust
                    and trust.get("decision")
                    in {
                        "suppressed_by_document_escalation",
                        "rejected",
                    }
                    and assertion.status == "failed"
                ):
                    soft_codes = {
                        "authority_mismatch",
                        "decision_mismatch",
                        "native_result_available_mismatch",
                        "visual_processing_required_mismatch",
                        "words_required",
                    }
                    hard = [f for f in assertion.failures if f.code not in soft_codes]
                    if not hard:
                        status = "document_escalation_observed"
                        assertion.notes.append(
                            "whole-document escalation; per-page soft mismatches ignored"
                        )
                report.add(
                    PageResultRow(
                        test_id=test_id,
                        page_number=page_number,
                        status=status,  # type: ignore[arg-type]
                        actual_authority=(str(trust.get("source_mode")) if trust else None),
                        actual_decision=str(trust.get("decision")) if trust else None,
                        reason_codes=(
                            [str(c) for c in (trust.get("reason_codes") or [])] if trust else []
                        ),
                        failure_codes=(
                            [f.code for f in assertion.failures] if status == "failed" else []
                        ),
                        notes=assertion.notes,
                    )
                )
                if status == "failed" and fail_fast:
                    break
        except Exception as exc:
            report.add(
                PageResultRow(
                    test_id="DOCUMENT",
                    page_number=0,
                    status="failed",
                    failure_codes=["runner_error"],
                    notes=[f"{_error_detail(exc)}: details suppressed"],
                )
            )
        finally:
            if session_id is not None:
                await delete_session(client, session_id)

    return report


def prepare_bundle(*, require_readme_checksums: bool = True) -> CorpusBundle:
    return validate_corpus(require_readme_checksums=require_readme_checksums)
