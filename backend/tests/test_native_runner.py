"""Subprocess runner tests for native extraction."""

from __future__ import annotations

from pathlib import Path

import pdfplumber
import pytest

from backend.app.contracts.errors import ErrorCode
from backend.app.extraction.native.errors import NativeExtractionError
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    NativeTrustPolicyConfig,
    NativeWorkerRequest,
)
from backend.app.extraction.native.runner import NativeExtractionRunner
from backend.app.processing.cancellation import CancellationToken


def _resolved_good_pdf() -> tuple[str, list[CanonicalPageRef]]:
    pdf = Path("fixtures/synthetic/native/good-native-single-page.pdf")
    resolved = str(pdf.resolve())
    with pdfplumber.open(pdf) as doc:
        page = doc.pages[0]
        pages = [CanonicalPageRef(1, float(page.width), float(page.height), 0, "pdf")]
    return resolved, pages


@pytest.mark.asyncio
async def test_worker_success(tmp_path: Path) -> None:
    pdf_resolved, pages = _resolved_good_pdf()
    request = NativeWorkerRequest(
        session_id="ses_" + ("a" * 32),
        document_id="doc_" + ("b" * 32),
        job_id="job_" + ("c" * 32),
        canonical_pdf_path=pdf_resolved,
        canonicalisation_method="original_pdf",
        pages=pages,
        policy=NativeTrustPolicyConfig(),
    )
    runner = NativeExtractionRunner(timeout_seconds=120, grace_seconds=2)
    outcome = await runner.run(request, staging_dir=tmp_path / "staging")
    assert outcome.exit_code == 0
    assert outcome.summary.pages_accepted >= 1
    assert outcome.pages[0].words


def test_worker_success_under_selector_event_loop(tmp_path: Path) -> None:
    """Windows uvicorn --reload uses SelectorEventLoop; Popen must still work."""

    import asyncio
    import sys

    pdf_resolved, pages = _resolved_good_pdf()
    request = NativeWorkerRequest(
        session_id="ses_" + ("a" * 32),
        document_id="doc_" + ("b" * 32),
        job_id="job_" + ("c" * 32),
        canonical_pdf_path=pdf_resolved,
        canonicalisation_method="original_pdf",
        pages=pages,
        policy=NativeTrustPolicyConfig(),
    )
    runner = NativeExtractionRunner(timeout_seconds=120, grace_seconds=2)
    staging = tmp_path / "staging-selector"

    async def _run() -> None:
        outcome = await runner.run(request, staging_dir=staging)
        assert outcome.exit_code == 0
        assert outcome.summary.pages_accepted >= 1
        assert outcome.pages[0].words

    if sys.platform == "win32":
        asyncio.run(_run(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(_run())


@pytest.mark.asyncio
async def test_worker_timeout(tmp_path: Path) -> None:
    pdf_resolved, pages = _resolved_good_pdf()
    request = NativeWorkerRequest(
        session_id="ses_" + ("a" * 32),
        document_id="doc_" + ("b" * 32),
        job_id="job_" + ("c" * 32),
        canonical_pdf_path=pdf_resolved,
        canonicalisation_method="original_pdf",
        pages=pages,
        policy=NativeTrustPolicyConfig(native_extraction_test_delay_seconds=5.0),
    )
    runner = NativeExtractionRunner(timeout_seconds=0.5, grace_seconds=0.2)
    with pytest.raises(NativeExtractionError) as exc:
        await runner.run(request, staging_dir=tmp_path / "staging")
    assert exc.value.code is ErrorCode.NATIVE_EXTRACTION_TIMEOUT


@pytest.mark.asyncio
async def test_worker_cancellation(tmp_path: Path) -> None:
    import asyncio

    from backend.app.processing.cancellation import JobCancelledError

    pdf_resolved, pages = _resolved_good_pdf()
    request = NativeWorkerRequest(
        session_id="ses_" + ("a" * 32),
        document_id="doc_" + ("b" * 32),
        job_id="job_" + ("c" * 32),
        canonical_pdf_path=pdf_resolved,
        canonicalisation_method="original_pdf",
        pages=pages,
        policy=NativeTrustPolicyConfig(native_extraction_test_delay_seconds=5.0),
    )
    token = CancellationToken()
    runner = NativeExtractionRunner(timeout_seconds=30, grace_seconds=0.5)

    async def cancel_soon() -> None:
        await asyncio.sleep(0.2)
        token.cancel()

    with pytest.raises(JobCancelledError):
        await asyncio.gather(
            runner.run(request, staging_dir=tmp_path / "staging", cancel_token=token),
            cancel_soon(),
        )


@pytest.mark.asyncio
async def test_self_check(tmp_path: Path) -> None:
    runner = NativeExtractionRunner(timeout_seconds=30, grace_seconds=1)
    assert await runner.self_check(tmp_path / "self")
