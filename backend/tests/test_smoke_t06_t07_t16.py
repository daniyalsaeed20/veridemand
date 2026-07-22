"""Smoke corpus regressions for T06 / T07 / T16 (near-overprint + sparse)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pdfplumber
import pytest
from scripts.smoke_corpus.split import split_page_to_pdf

from backend.app.contracts.native import NativePageDecision, NativePageResult, SourceMode
from backend.app.contracts.warnings import NativeReasonCode
from backend.app.extraction.native.geometry_quality import GeometryMetrics
from backend.app.extraction.native.metrics import build_page_metrics
from backend.app.extraction.native.models import CanonicalPageRef, NativeTrustPolicyConfig
from backend.app.extraction.native.near_overprint import (
    interleaved_double_ratio,
    max_consecutive_double_pair_run,
)
from backend.app.extraction.native.pdfplumber_extractor import extract_page_candidates
from backend.app.extraction.native.serializer import build_page_result
from backend.app.extraction.native.trust_policy import PageTrustDecisionBundle, decide_page_trust
from backend.app.settings.config import Settings

SMOKE_DIR = Path("fixtures/synthetic/smoke")
SMOKE_PDF = SMOKE_DIR / "VeriDemand_Synthetic_PDF_Regression_Corpus_v1.0.pdf"
SMOKE_MANIFEST = SMOKE_DIR / "VeriDemand_Synthetic_PDF_Regression_Manifest_v1.0.json"


def _manifest_page(test_id: str) -> dict[str, Any]:
    data = json.loads(SMOKE_MANIFEST.read_text(encoding="utf-8"))
    pages = data["pages"]
    if not isinstance(pages, list):
        raise AssertionError("smoke manifest pages[] missing")
    for entry in pages:
        if isinstance(entry, dict) and entry.get("test_id") == test_id:
            return entry
    raise AssertionError(f"{test_id} missing from smoke manifest")


def _decide_split(
    tmp_path: Path, test_id: str
) -> tuple[PageTrustDecisionBundle, NativePageResult, GeometryMetrics]:
    entry = _manifest_page(test_id)
    page_number = int(entry["page_number"])
    split = tmp_path / f"{test_id}.pdf"
    split_page_to_pdf(SMOKE_PDF, page_number, split)
    policy = NativeTrustPolicyConfig()
    with pdfplumber.open(split) as doc:
        page = doc.pages[0]
        refs = [
            CanonicalPageRef(
                page_number=1,
                width_points=float(page.width),
                height_points=float(page.height),
                intrinsic_rotation=0,
                source_type="pdf",
            )
        ]
    candidates = extract_page_candidates(split, refs, policy)
    candidate = candidates[0]
    metrics, geometry_m, unicode_m, text_m, image_m = build_page_metrics(candidate, policy)
    bundle = decide_page_trust(
        candidate,
        metrics=metrics,
        geometry_m=geometry_m,
        unicode_m=unicode_m,
        text_m=text_m,
        image_m=image_m,
        policy=policy,
        source_type="pdf",
    )
    result = build_page_result(bundle, canonicalisation_method="original_pdf")
    return bundle, result, geometry_m


@pytest.fixture(scope="module")
def _require_smoke() -> None:
    if not SMOKE_PDF.is_file() or not SMOKE_MANIFEST.is_file():
        pytest.skip("smoke corpus PDF/manifest missing")


def test_native_trust_threshold_unchanged(_require_smoke: None) -> None:
    assert Settings().native_trust_threshold == 0.75
    assert NativeTrustPolicyConfig().native_trust_threshold == 0.75


def test_t06_never_publishes_interleaved_doubles(tmp_path: Path, _require_smoke: None) -> None:
    bundle, result, geometry_m = _decide_split(tmp_path, "T06")
    assert geometry_m.hard_rule_path in {"A", "B", "none"}
    if bundle.accept_text:
        text = result.provisional_native_text or ""
        assert interleaved_double_ratio(text) < 0.35
        assert max_consecutive_double_pair_run(text) < 4
        assert bundle.trust.source_mode is SourceMode.NATIVE_AUTHORITY
    else:
        assert bundle.trust.decision is NativePageDecision.REJECTED
        assert bundle.trust.source_mode is SourceMode.VISUAL_AUTHORITY
        assert (
            NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value in bundle.trust.reason_codes
        )
        assert result.words == []
        assert result.characters == []


def test_t07_never_publishes_duplicate_header_footer(tmp_path: Path, _require_smoke: None) -> None:
    bundle, result, geometry_m = _decide_split(tmp_path, "T07")
    assert geometry_m.hard_rule_path in {"A", "B", "none"}
    if bundle.accept_text:
        text = (result.provisional_native_text or "").replace(" ", "").upper()
        assert "SSYYNNTTHHEETTIICC" not in text
        assert "BILILLININGG" not in text
        assert interleaved_double_ratio(result.provisional_native_text or "") < 0.35
        assert max_consecutive_double_pair_run(result.provisional_native_text or "") < 4
    else:
        assert bundle.trust.decision is NativePageDecision.REJECTED
        assert bundle.trust.source_mode is SourceMode.VISUAL_AUTHORITY
        assert (
            NativeReasonCode.EXCESSIVE_NEAR_OVERPRINT_DUPLICATES.value in bundle.trust.reason_codes
        )
        assert result.words == []
        assert result.characters == []


def test_t16_sparse_before_trust(_require_smoke: None, tmp_path: Path) -> None:
    entry = _manifest_page("T16")
    split = tmp_path / "T16.pdf"
    split_page_to_pdf(SMOKE_PDF, int(entry["page_number"]), split)
    min_chars = Settings().native_min_characters
    with pdfplumber.open(split) as doc:
        page = doc.pages[0]
        chars = [
            c
            for c in (page.chars or [])
            if isinstance(c.get("text"), str) and not str(c["text"]).isspace()
        ]
    assert len(chars) < min_chars
    assert len(chars) > 0

    bundle, result, _ = _decide_split(tmp_path, "T16")
    assert bundle.trust.decision is NativePageDecision.REJECTED
    assert NativeReasonCode.NATIVE_TEXT_TOO_SPARSE.value in bundle.trust.reason_codes
    assert result.words == []
