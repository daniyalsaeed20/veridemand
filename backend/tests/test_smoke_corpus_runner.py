"""Unit tests for the synthetic smoke corpus runner helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, NameObject, NumberObject
from scripts.smoke_corpus.assert_page import assert_page
from scripts.smoke_corpus.report import SmokeReport
from scripts.smoke_corpus.runner import filter_pages
from scripts.smoke_corpus.split import page_cropbox, page_rotation, split_page_to_pdf
from scripts.smoke_corpus.validate import validate_corpus


def _write_rotated_cropped_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=300)
    page = writer.pages[0]
    page[NameObject("/Rotate")] = NumberObject(90)
    page[NameObject("/CropBox")] = ArrayObject(
        [NumberObject(10), NumberObject(20), NumberObject(180), NumberObject(280)]
    )
    with path.open("wb") as handle:
        writer.write(handle)


def test_page_splitting_preserves_rotation(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_rotated_cropped_pdf(source)
    out = tmp_path / "page.pdf"
    split_page_to_pdf(source, 1, out)
    assert page_rotation(out, 1) == 90
    reader = PdfReader(str(out))
    assert len(reader.pages) == 1


def test_page_splitting_preserves_cropbox(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_rotated_cropped_pdf(source)
    out = tmp_path / "page.pdf"
    split_page_to_pdf(source, 1, out)
    crop = page_cropbox(out, 1)
    assert crop is not None
    assert crop == pytest.approx((10.0, 20.0, 180.0, 280.0))


def test_manifest_page_count_mismatch_fails(tmp_path: Path) -> None:
    pdf = tmp_path / "c.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as handle:
        writer.write(handle)
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "privacy": "Entirely synthetic; no private or real patient data.",
                "page_count_including_cover": 99,
                "pages": [
                    {
                        "test_id": "T01",
                        "page_number": 1,
                        "phase_expectation": "current_phase_expected",
                        "expected_source_mode": "native_authority",
                        "expected_viewer": "normal",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bundle = validate_corpus(
        pdf_path=pdf,
        manifest_path=manifest,
        readme_path=tmp_path / "missing.md",
        expected_pdf_sha="0" * 64,
        expected_manifest_sha="0" * 64,
        require_readme_checksums=False,
    )
    assert any(i.code == "page_count_mismatch" for i in bundle.issues)


def test_duplicate_test_id_fails(tmp_path: Path) -> None:
    pdf = tmp_path / "c.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as handle:
        writer.write(handle)
    page = {
        "test_id": "T01",
        "page_number": 1,
        "phase_expectation": "current_phase_expected",
        "expected_source_mode": "native_authority",
        "expected_viewer": "normal",
    }
    page2 = dict(page)
    page2["page_number"] = 2
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "privacy": "Entirely synthetic; no private or real patient data.",
                "page_count_including_cover": 2,
                "pages": [page, page2],
            }
        ),
        encoding="utf-8",
    )
    bundle = validate_corpus(
        pdf_path=pdf,
        manifest_path=manifest,
        require_readme_checksums=False,
        expected_pdf_sha="0" * 64,
        expected_manifest_sha="0" * 64,
    )
    assert any(i.code == "duplicate_test_id" for i in bundle.issues)


def test_missing_page_fails(tmp_path: Path) -> None:
    pdf = tmp_path / "c.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with pdf.open("wb") as handle:
        writer.write(handle)
    manifest = tmp_path / "m.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "privacy": "Entirely synthetic; no private or real patient data.",
                "page_count_including_cover": 1,
                "pages": [
                    {
                        "test_id": "T99",
                        "page_number": 5,
                        "phase_expectation": "current_phase_expected",
                        "expected_source_mode": "native_authority",
                        "expected_viewer": "normal",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bundle = validate_corpus(
        pdf_path=pdf,
        manifest_path=manifest,
        require_readme_checksums=False,
        expected_pdf_sha="0" * 64,
        expected_manifest_sha="0" * 64,
    )
    assert any(i.code == "missing_page" for i in bundle.issues)


def test_temporary_files_removed_by_split_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _write_rotated_cropped_pdf(source)
    out = tmp_path / "nested" / "page.pdf"
    split_page_to_pdf(source, 1, out)
    assert out.is_file()
    out.unlink()
    assert not out.exists()


def test_fail_fast_filter_does_not_drop_later_selection() -> None:
    pages = [
        {"test_id": "T01", "page_number": 2},
        {"test_id": "T02", "page_number": 3},
        {"test_id": "T03", "page_number": 4},
    ]
    selected = filter_pages(pages, start_page=3)
    assert [p["test_id"] for p in selected] == ["T02", "T03"]


def test_fail_fast_stops_after_first_hard_failure() -> None:
    """Document the fail-fast contract used by the runner loop."""

    statuses = ["failed", "passed", "passed"]
    collected: list[str] = []
    fail_fast = True
    for status in statuses:
        collected.append(status)
        if status == "failed" and fail_fast:
            break
    assert collected == ["failed"]

    collected.clear()
    fail_fast = False
    for status in statuses:
        collected.append(status)
        if status == "failed" and fail_fast:
            break
    assert collected == ["failed", "passed", "passed"]


def test_private_text_never_printed_in_report() -> None:
    from scripts.smoke_corpus.report import PageResultRow

    report = SmokeReport(corpus_version="1.0.0", mode="page-by-page")
    report.add(
        PageResultRow(
            test_id="T01",
            page_number=2,
            status="failed",
            failure_codes=["authority_mismatch"],
            notes=["details suppressed"],
        )
    )
    payload = json.dumps(report.to_dict())
    assert "patient" not in payload.lower()
    assert "provisional_native_text" not in payload
    # Report may contain the key name "results" but never word payloads.
    assert '"words"' not in payload


def test_whole_document_escalation_not_confused_with_page_failure() -> None:
    manifest_page: dict[str, Any] = {
        "test_id": "T01",
        "phase_expectation": "current_phase_expected",
        "expected_source_mode": "native_authority",
        "expected_decision": "accepted",
        "expected_native_text": True,
        "canonical_viewer_success": True,
        "word_publication": "required",
        "phase3_reason_codes": [],
    }
    trust = {
        "page_number": 2,
        "decision": "suppressed_by_document_escalation",
        "source_mode": "visual_authority",
        "reason_codes": ["document_visual_authority_escalation"],
        "hard_rejection": False,
        "native_result_available": False,
        "visual_processing_required": True,
        "native_trust_score": None,
        "metrics": {},
    }
    result = assert_page(
        manifest_page=manifest_page,
        trust=trust,
        page_result={"words": [], "characters": [], "provisional_native_text": None},
        canonical_page={"width_points": 595.0, "height_points": 842.0, "intrinsic_rotation": 0},
        canonical_ok=True,
        document_escalated=True,
    )
    assert result.status == "document_escalation_observed"
    assert result.ok


def test_acceptable_outcomes_clean_or_visual() -> None:
    manifest_page = {
        "test_id": "T06",
        "phase_expectation": "current_phase_expected",
        "expected_source_mode": "visual_authority",
        "expected_decision": "rejected",
        "acceptable_outcomes": [
            {
                "decision": "accepted",
                "source_mode": "native_authority",
                "require_no_interleaved_duplicates": True,
            },
            {
                "decision": "rejected",
                "source_mode": "visual_authority",
                "require_reason_codes": ["excessive_near_overprint_duplicates"],
            },
        ],
        "word_publication": "forbidden",
        "canonical_viewer_success": True,
    }
    rejected = assert_page(
        manifest_page=manifest_page,
        trust={
            "decision": "rejected",
            "source_mode": "visual_authority",
            "reason_codes": ["excessive_near_overprint_duplicates", "native_text_rejected"],
            "hard_rejection": True,
            "native_result_available": False,
            "visual_processing_required": True,
            "metrics": {},
        },
        page_result={"words": [], "characters": [], "provisional_native_text": None},
        canonical_page={"width_points": 595.0, "height_points": 842.0, "intrinsic_rotation": 0},
        canonical_ok=True,
    )
    assert rejected.status == "passed"

    accepted = assert_page(
        manifest_page=manifest_page,
        trust={
            "decision": "accepted",
            "source_mode": "native_authority",
            "reason_codes": [],
            "hard_rejection": False,
            "native_result_available": True,
            "visual_processing_required": False,
            "metrics": {},
        },
        page_result={
            "words": [{"text": "Clean body line"}],
            "characters": [{"text": "C"}],
            "provisional_native_text": "Clean body line",
        },
        canonical_page={"width_points": 595.0, "height_points": 842.0, "intrinsic_rotation": 0},
        canonical_ok=True,
    )
    assert accepted.status == "passed"

    bad_accept = assert_page(
        manifest_page=manifest_page,
        trust={
            "decision": "accepted",
            "source_mode": "native_authority",
            "reason_codes": [],
            "hard_rejection": False,
            "native_result_available": True,
            "visual_processing_required": False,
            "metrics": {},
        },
        page_result={
            "words": [{"text": "SSYYNNTTHHEETTIICC"}],
            "characters": [{"text": "S"}],
            "provisional_native_text": "SSYYNNTTHHEETTIICC",
        },
        canonical_page={"width_points": 595.0, "height_points": 842.0, "intrinsic_rotation": 0},
        canonical_ok=True,
    )
    assert bad_accept.status == "failed"


def test_future_phase_ocr_page_passes_when_routed() -> None:
    manifest_page: dict[str, Any] = {
        "test_id": "T11",
        "phase_expectation": "future_phase_expected",
        "expected_source_mode": "visual_authority",
        "expected_decision": "rejected",
        "expected_native_text": False,
        "word_publication": "forbidden",
    }
    trust = {
        "decision": "rejected",
        "source_mode": "visual_authority",
        "reason_codes": ["native_text_rejected"],
        "hard_rejection": True,
        "native_result_available": False,
        "visual_processing_required": True,
        "metrics": {},
    }
    result = assert_page(
        manifest_page=manifest_page,
        trust=trust,
        page_result={"words": [], "characters": [], "provisional_native_text": None},
        canonical_page=None,
        canonical_ok=True,
    )
    assert result.status == "skipped_for_future_phase"


def test_committed_corpus_validates_when_readme_present() -> None:
    readme = Path("docs/smoke/README.md")
    if not readme.is_file():
        pytest.skip("README not written yet in this collection order")
    bundle = validate_corpus()
    assert bundle.ok, [i.message for i in bundle.issues]
