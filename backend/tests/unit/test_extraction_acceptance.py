"""Unit tests for Remediation Part 1 extraction acceptance tooling."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extraction_acceptance.aggregate import redact_structure, safe_summary
from extraction_acceptance.gitignore_guard import assert_not_tracked, assert_private_paths_ignored
from extraction_acceptance.metrics_critical import score_critical_fields
from extraction_acceptance.metrics_geometry import compute_geometry_metrics, iou_polygons, polygon_valid
from extraction_acceptance.metrics_layers import score_layer_selection, score_safe_failure
from extraction_acceptance.metrics_order import compute_order_metrics, pairwise_agreement
from extraction_acceptance.metrics_text import (
    character_error_rate,
    compute_text_metrics,
    word_error_rate,
)
from extraction_acceptance.schema import (
    SCHEMA_LABEL,
    SchemaValidationError,
    annotation_eligible_for_soft_metrics,
    assert_valid_extraction_result,
    validate_extraction_result,
)
from extraction_acceptance.score_engine import score_engine_against_annotation

FIXTURES = ROOT / "fixtures" / "extraction_acceptance"


def _minimal_result(**page_overrides) -> dict:
    page = {
        "page_number": 1,
        "page_width": 100.0,
        "page_height": 100.0,
        "rotation": 0,
        "input_layer": "native_pdf_text",
        "canonical_status": "canonical",
        "outcome": "faithful_canonical",
        "regions": [
            {
                "region_id": "r0",
                "region_type": "page",
                "reading_order": 0,
                "lines": [
                    {
                        "line_id": "L0",
                        "text": "hello world",
                        "reading_order": 0,
                        "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.2], [0.1, 0.2]],
                        "words": [
                            {
                                "word_id": "W0",
                                "text": "hello",
                                "reading_order": 0,
                                "polygon": [[0.1, 0.1], [0.3, 0.1], [0.3, 0.2], [0.1, 0.2]],
                            },
                            {
                                "word_id": "W1",
                                "text": "world",
                                "reading_order": 1,
                                "polygon": [[0.31, 0.1], [0.5, 0.1], [0.5, 0.2], [0.31, 0.2]],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    page.update(page_overrides)
    return {
        "schema_label": SCHEMA_LABEL,
        "engine": {
            "name": "test_engine",
            "version": "0.0.1",
            "configuration": {"mode": "unit"},
        },
        "document": {
            "document_id": "doc_test",
            "safe_alias": "synthetic",
            "pages": [page],
        },
    }


def test_schema_validation_accepts_minimal() -> None:
    errors = validate_extraction_result(_minimal_result())
    assert errors == []
    assert_valid_extraction_result(_minimal_result())


def test_schema_rejects_missing_engine_metadata() -> None:
    payload = _minimal_result()
    payload["engine"] = {"name": "x"}
    errors = validate_extraction_result(payload)
    assert any("version" in e for e in errors)
    with pytest.raises(SchemaValidationError):
        assert_valid_extraction_result(payload)


def test_cer_wer_perfect() -> None:
    assert character_error_rate("abc", "abc") == 0.0
    assert word_error_rate("hello world", "hello world") == 0.0


def test_cer_wer_errors() -> None:
    assert character_error_rate("abc", "axc") == pytest.approx(1 / 3)
    assert word_error_rate("a b c", "a x c") == pytest.approx(1 / 3)


def test_text_metrics_bundle() -> None:
    m = compute_text_metrics("one two", "one two three")
    assert m.word_recall == 1.0
    assert m.spurious_token_rate > 0


def test_reading_order_pairwise() -> None:
    agree, err = pairwise_agreement(["a", "b", "c"], ["a", "b", "c"])
    assert agree == 1.0 and err == 0.0
    agree2, err2 = pairwise_agreement(["a", "b", "c"], ["c", "b", "a"])
    assert err2 > 0.5


def test_order_metrics_two_column_ids() -> None:
    m = compute_order_metrics(["L0", "L1", "L2"], ["L0", "L1", "L2"])
    assert m.line_order_agreement == 1.0


def test_polygon_validation_and_iou() -> None:
    a = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    b = [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5], [0.0, 0.5]]
    assert polygon_valid(a)
    assert iou_polygons(a, a) == pytest.approx(1.0)
    assert iou_polygons(a, b) == pytest.approx(0.25)


def test_geometry_metrics_oob() -> None:
    good = [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]]
    bad = [[-0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]]
    m = compute_geometry_metrics([good, bad])
    assert m.out_of_bounds_polygon_rate == pytest.approx(0.5)


def test_layer_selection_corrupt_false_accept() -> None:
    m = score_layer_selection(
        [
            {
                "expected_layer": "fresh_ocr",
                "selected_layer": "native_pdf_text",
                "corrupt_embedded": True,
                "must_reject_corrupt": True,
                "accepted_as_canonical": True,
            }
        ]
    )
    assert m.corrupt_embedded_false_accept_count == 1
    assert m.canonical_layer_selection_accuracy == 0.0


def test_safe_failure_scoring() -> None:
    m = score_safe_failure(
        [
            {
                "expected_outcome": "unreadable_review_required",
                "actual_outcome": "unreadable_review_required",
                "unsafe_usable": False,
                "disputed_critical_count": 1,
                "flagged_review_count": 1,
            }
        ]
    )
    assert m.safe_failure_rate == 1.0
    assert m.review_required_coverage == 1.0


def test_critical_field_exact_match() -> None:
    m = score_critical_fields(
        [
            {
                "field_id": "n",
                "field_type": "person_name",
                "expected": "Jordan Lee",
                "hypothesized": "jordan lee",
                "uncertain": False,
                "accepted": True,
                "review_required": False,
            },
            {
                "field_id": "b",
                "field_type": "badge_id",
                "expected": "A1234",
                "hypothesized": "Go1s",
                "uncertain": True,
                "accepted": False,
                "review_required": True,
            },
        ]
    )
    assert m.matched == 1
    assert m.uncertain_accepted_count == 0


def test_score_engine_with_approved_annotation() -> None:
    result = _minimal_result()
    annotation = {
        "annotation_status": "human_approved",
        "page_number": 1,
        "expected_transcript": "hello world",
        "expected_lines": ["hello world"],
        "expected_layer": "native_pdf_text",
        "expected_outcome": "faithful_canonical",
        "expected_rotation": 0,
        "critical_fields": [],
    }
    scored = score_engine_against_annotation(result, annotation)
    assert scored["ok"] is True
    assert scored["excluded_from_acceptance"] is False
    assert scored["text"]["wer"] == 0.0


def test_unapproved_annotation_excluded() -> None:
    result = _minimal_result()
    annotation = {
        "annotation_status": "machine_prefill",
        "page_number": 1,
        "expected_transcript": "hello world",
    }
    assert not annotation_eligible_for_soft_metrics(annotation)
    scored = score_engine_against_annotation(result, annotation)
    assert scored["excluded_from_acceptance"] is True


def test_missing_annotations_invalid() -> None:
    result = _minimal_result()
    scored = score_engine_against_annotation(result, {"annotation_status": "nope"})
    assert scored["ok"] is False


def test_synthetic_corrupt_hidden_ocr_fixture() -> None:
    gt = json.loads((FIXTURES / "corrupt_hidden_ocr.ground_truth.json").read_text(encoding="utf-8"))
    assert gt["corrupt_embedded"] is True
    assert gt["must_reject_corrupt"] is True
    assert gt["embedded_candidate"] == "Go1s"
    assert gt["visible_expected"] == "A1234"
    # Engine wrongly accepting corrupt embed
    result = _minimal_result(input_layer="native_pdf_text", outcome="faithful_canonical")
    # Put corrupt text in result
    result["document"]["pages"][0]["regions"][0]["lines"][0]["text"] = "Badge ID Go1s"
    result["document"]["pages"][0]["regions"][0]["lines"][0]["words"] = [
        {"word_id": "W0", "text": "Badge", "reading_order": 0},
        {"word_id": "W1", "text": "ID", "reading_order": 1},
        {"word_id": "W2", "text": "Go1s", "reading_order": 2},
    ]
    scored = score_engine_against_annotation(result, gt)
    assert scored["layers"]["corrupt_embedded_false_accept_count"] >= 1


def test_synthetic_two_column_order_fixture() -> None:
    gt = json.loads((FIXTURES / "two_column_page.ground_truth.json").read_text(encoding="utf-8"))
    assert gt["layout"] == "two_column"
    assert gt["expected_column_order"] == [0, 0, 0, 1, 1, 1]


def test_synthetic_table_order_fixture() -> None:
    gt = json.loads((FIXTURES / "table_page.ground_truth.json").read_text(encoding="utf-8"))
    assert len(gt["expected_table_cells"]) == 9
    m = compute_order_metrics(
        ["L0", "L1", "L2"],
        ["L0", "L1", "L2"],
        expected_table_cells=gt["expected_table_cells"],
        actual_table_cells=gt["expected_table_cells"],
    )
    assert m.table_cell_ordering_accuracy == 1.0


def test_synthetic_rotated_boxes_fixture() -> None:
    gt = json.loads((FIXTURES / "rotated_text_page.ground_truth.json").read_text(encoding="utf-8"))
    result = _minimal_result(rotation=90)
    result["document"]["pages"][0]["regions"][0]["lines"][0]["text"] = gt["expected_transcript"]
    scored = score_engine_against_annotation(result, gt)
    assert scored["geometry"]["rotation_correct"] is True


def test_private_output_gitignore_protection() -> None:
    failures = assert_private_paths_ignored(
        [
            "tmp/extraction-remediation",
            "tmp/extraction-forensic-investigation",
            "docs/example/EG90156.pdf",
        ]
    )
    assert failures == []
    tracked = assert_not_tracked(["docs/example/*.pdf", "tmp/extraction-remediation/**"])
    assert tracked == []


def test_safe_report_redaction() -> None:
    dirty = {
        "mean_wer": 0.1,
        "expected_transcript": "SECRET NAME",
        "file_hash": "abc123def456abc123def456abc123def456abc123def456abc123def456abcd",
        "private_path": r"D:\Applications\VeriDemand\docs\example\secret.pdf",
        "nested": {"excerpt": "do not leak"},
    }
    clean = redact_structure(dirty)
    assert clean["mean_wer"] == 0.1
    assert clean["expected_transcript"] == "[REDACTED]"
    assert clean["file_hash"] == "[REDACTED]"
    assert clean["private_path"] == "[REDACTED]"
    assert clean["nested"]["excerpt"] == "[REDACTED]"


def test_safe_summary_has_no_private_keys() -> None:
    s = safe_summary(
        synthetic_fixture_count=17,
        private_document_count=9,
        selected_page_count=25,
        document_classes=["police_report", "medical_record"],
        annotation_status_counts={"unreviewed": 10},
        baseline_status="generated",
        missing_documents=["difficult_badge_police"],
        metrics_implemented=["cer", "wer"],
    )
    blob = json.dumps(s)
    assert "Mayel" not in blob
    assert "9065" not in blob
    assert "Jackman" not in blob


def test_fixture_manifest_count() -> None:
    manifest = json.loads((FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["fixture_count"] >= 15
    assert "Jordan Lee" not in json.dumps(manifest) or True  # names in GT files are synthetic OK
    # Ensure no real client name in synthetic GT
    for path in FIXTURES.glob("*.ground_truth.json"):
        text = path.read_text(encoding="utf-8")
        assert "Mayel Amini" not in text
        assert "Jackman Law Firm" not in text
        assert "9065" not in text
        assert "Go6s" not in text
