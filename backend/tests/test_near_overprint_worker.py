"""Private / synthetic worker regressions for Phase 3.5 near-overprint hard reject."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pdfplumber
import pytest

from backend.app.contracts.native import NativePageDecision, SourceMode
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.models import (
    CanonicalPageRef,
    NativeTrustPolicyConfig,
    NativeWorkerRequest,
)
from backend.app.extraction.native.near_overprint import interleaved_double_ratio
from backend.app.extraction.native.runner import NativeExtractionRunner

PRIVATE_DIR = Path("fixtures/private")
MANIFEST = PRIVATE_DIR / "native-trust-manifest.local.json"
SYNTHETIC_DIR = Path("fixtures/synthetic/native")


def _load_manifest() -> dict[str, Any]:
    if not MANIFEST.is_file():
        return {}
    raw: object = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items()}


def _page_refs(pdf_path: Path, page_numbers: list[int] | None = None) -> list[CanonicalPageRef]:
    """Build canonical refs. If page_numbers is None, include every page (required by worker)."""

    refs: list[CanonicalPageRef] = []
    with pdfplumber.open(pdf_path) as doc:
        indices = range(len(doc.pages)) if page_numbers is None else [n - 1 for n in page_numbers]
        for idx in indices:
            page = doc.pages[idx]
            refs.append(CanonicalPageRef(idx + 1, float(page.width), float(page.height), 0, "pdf"))
    return refs


def _assert_clean_or_visual(page_result: Any) -> None:
    """Accepted text must be single-copy; else visual_authority with empty text."""

    if page_result.decision == NativePageDecision.ACCEPTED:
        text = page_result.provisional_native_text or ""
        assert interleaved_double_ratio(text) < 0.35
        return

    assert page_result.decision is NativePageDecision.REJECTED
    assert page_result.source_mode is SourceMode.VISUAL_AUTHORITY
    assert page_result.trust.hard_rejection
    assert (
        NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value in page_result.trust.reason_codes
    )
    assert not page_result.words
    assert not page_result.characters
    assert page_result.provisional_native_text in (None, "")


@pytest.mark.asyncio
async def test_synthetic_multi_cluster_worker_never_publishes_doubles(tmp_path: Path) -> None:
    pdf = SYNTHETIC_DIR / "multi-displacement-clusters.pdf"
    if not pdf.is_file():
        pytest.skip("synthetic multi-displacement fixture missing; run generate_native.py")
    pages = _page_refs(pdf, [1])
    request = NativeWorkerRequest(
        session_id="ses_" + ("d" * 32),
        document_id="doc_" + ("e" * 32),
        job_id="job_" + ("f" * 32),
        canonical_pdf_path=str(pdf.resolve()),
        canonicalisation_method="original_pdf",
        pages=pages,
        policy=NativeTrustPolicyConfig(),
    )
    outcome = await NativeExtractionRunner(timeout_seconds=120, grace_seconds=2).run(
        request, staging_dir=tmp_path / "staging-multi"
    )
    assert outcome.exit_code == 0
    _assert_clean_or_visual(outcome.pages[0])


@pytest.mark.asyncio
async def test_synthetic_diluted_region_worker_never_publishes_doubles(tmp_path: Path) -> None:
    pdf = SYNTHETIC_DIR / "diluted-coverage-duplicate-region.pdf"
    if not pdf.is_file():
        pytest.skip("synthetic diluted-region fixture missing; run generate_native.py")
    pages = _page_refs(pdf, [1])
    request = NativeWorkerRequest(
        session_id="ses_" + ("1" * 32),
        document_id="doc_" + ("2" * 32),
        job_id="job_" + ("3" * 32),
        canonical_pdf_path=str(pdf.resolve()),
        canonicalisation_method="original_pdf",
        pages=pages,
        policy=NativeTrustPolicyConfig(),
    )
    outcome = await NativeExtractionRunner(timeout_seconds=120, grace_seconds=2).run(
        request, staging_dir=tmp_path / "staging-diluted"
    )
    assert outcome.exit_code == 0
    _assert_clean_or_visual(outcome.pages[0])


@pytest.mark.asyncio
async def test_private_pages_3_and_5_worker_regression(tmp_path: Path) -> None:
    """Real-worker regression for production pages 3 and 5 (skip if local fixture absent).

    Manifest key `near_overprint_multi_cluster` may be:
      - a relative PDF filename (pages default to [3, 5]), or
      - {"file": "opaque.pdf", "pages": [3, 5]}
    Assertions never embed private text literals.
    """

    manifest = _load_manifest()
    entry = manifest.get("near_overprint_multi_cluster")
    if not entry:
        pytest.skip("private near_overprint_multi_cluster manifest entry not configured")

    if isinstance(entry, str):
        rel = entry
        page_numbers = [3, 5]
    elif isinstance(entry, dict):
        rel = str(entry.get("file") or entry.get("path") or "")
        pages_raw = entry.get("pages") or [3, 5]
        page_numbers = [int(p) for p in pages_raw]
    else:
        pytest.skip("unsupported near_overprint_multi_cluster manifest shape")

    pdf = PRIVATE_DIR / rel
    if not pdf.is_file():
        pytest.skip(f"private PDF for near_overprint_multi_cluster missing: {rel!r}")

    # Worker requires one CanonicalPageRef per document page (page_count match).
    pages = _page_refs(pdf, page_numbers=None)
    request = NativeWorkerRequest(
        session_id="ses_" + ("a" * 32),
        document_id="doc_" + ("b" * 32),
        job_id="job_" + ("c" * 32),
        canonical_pdf_path=str(pdf.resolve()),
        canonicalisation_method="original_pdf",
        pages=pages,
        policy=NativeTrustPolicyConfig(),
    )
    outcome = await NativeExtractionRunner(timeout_seconds=300, grace_seconds=2).run(
        request, staging_dir=tmp_path / "staging-private-nop"
    )
    assert outcome.exit_code == 0
    by_num = {p.page_number: p for p in outcome.pages}
    for n in page_numbers:
        assert n in by_num
        _assert_clean_or_visual(by_num[n])
