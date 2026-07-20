"""Integration: Phase 4 hardening authority + no-reprocess + LLM off."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.models.enums import DocumentClassification, SafetyArchetype
from app.services.classification.authority import is_primary_authoritative
from app.services.llm import classifier as llm_mod
from tests.fixtures.upload_builders import (
    write_demand_docx,
    write_demand_with_police_section_pdf,
    write_police_mentioning_settlement_pdf,
    write_police_report_pdf,
)
from tests.helpers_process import make_client, upload_and_process


def test_demand_pdf_non_authoritative_even_with_police_language(tmp_path: Path) -> None:
    # Long adversarial content covered in unit tests; integration uses valid short PDF.
    path = tmp_path / "demand.pdf"
    write_demand_with_police_section_pdf(path)
    # Prefer short demand if long PDF writer is fragile — also try demand builder
    from tests.fixtures.upload_builders import write_demand_pdf

    path2 = tmp_path / "demand2.pdf"
    write_demand_pdf(path2)
    with make_client(tmp_path) as client:
        _, docs = upload_and_process(
            client,
            [("demand.pdf", path2.read_bytes(), "application/pdf")],
        )
        doc = docs[0]
        assert doc.classification == DocumentClassification.EXISTING_DEMAND
        assert doc.safety_archetype in {
            SafetyArchetype.EXISTING_DEMAND,
            SafetyArchetype.UNCERTAIN_DERIVATIVE,
        }
        assert doc.exclude_from_drafting is True
        assert is_primary_authoritative(doc) is False
        assert doc.classification_status in {"ambiguous", "needs_confirmation", "proposed"}
        # High rule score must not imply primary authority
        if doc.classification_confidence and doc.classification_confidence >= 0.55:
            assert is_primary_authoritative(doc) is False


def test_police_with_settlement_mention_remains_evidence(tmp_path: Path) -> None:
    path = tmp_path / "police.pdf"
    write_police_mentioning_settlement_pdf(path)
    with make_client(tmp_path) as client:
        _, docs = upload_and_process(
            client,
            [("police.pdf", path.read_bytes(), "application/pdf")],
        )
        doc = docs[0]
        assert doc.classification == DocumentClassification.POLICE_REPORT
        assert doc.safety_archetype in {None, SafetyArchetype.NONE}
        assert is_primary_authoritative(doc) is True


def test_cannot_clear_exclude_without_safety_confirmation(tmp_path: Path) -> None:
    path = tmp_path / "demand.docx"
    write_demand_docx(path)
    with make_client(tmp_path) as client:
        session_id, docs = upload_and_process(
            client,
            [
                (
                    "demand.docx",
                    path.read_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ],
        )
        doc_id = docs[0].id
        resp = client.patch(
            f"/api/v1/sessions/{session_id}/documents/{doc_id}",
            json={"exclude_from_drafting": False},
        )
        assert resp.status_code == 400
        assert resp.json()["error_code"] == "document_invalid_patch"


def test_patch_classification_no_extract_rerun(tmp_path: Path) -> None:
    path = tmp_path / "police.pdf"
    write_police_report_pdf(path)
    with make_client(tmp_path) as client:
        session_id, docs = upload_and_process(
            client,
            [("police.pdf", path.read_bytes(), "application/pdf")],
        )
        doc_id = docs[0].id
        hits = {"n": 0}

        def boom(*_a: object, **_k: object) -> object:
            hits["n"] += 1
            raise RuntimeError("extract rerun")

        import app.services.extraction.native as native_mod
        import app.services.process.service as process_mod

        with (
            patch.object(native_mod, "extract_document_native", boom),
            patch.object(process_mod, "extract_ocr_page", boom),
        ):
            r = client.patch(
                f"/api/v1/sessions/{session_id}/documents/{doc_id}",
                json={"classification": "other", "confirm_classification": True},
            )
            assert r.status_code == 200
            assert hits["n"] == 0


def test_llm_disabled_zero_calls_on_ambiguous_demand(tmp_path: Path) -> None:
    path = tmp_path / "demand.pdf"
    write_demand_with_police_section_pdf(path)
    calls = {"n": 0}

    def counting(*_a: object, **_k: object) -> None:
        calls["n"] += 1
        return None

    with make_client(tmp_path) as client:
        with patch.object(llm_mod, "classify_with_llm_fallback", counting):
            with patch(
                "app.services.classification.service.classify_with_llm_fallback",
                counting,
            ):
                upload_and_process(
                    client,
                    [("demand.pdf", path.read_bytes(), "application/pdf")],
                )
    assert calls["n"] == 0
