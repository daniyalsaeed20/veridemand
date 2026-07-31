"""Phase 5 Task 3D coverage-event, worklist, report, and server hardening tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from PIL import Image, ImageDraw

from backend.app.datasets.phase5.coverage import (
    build_coverage_aggregate,
    build_coverage_review,
    current_coverage_state,
    page_artefact_hashes,
    render_coverage_aggregate_markdown,
    verify_coverage_artefacts,
    verify_coverage_events,
    write_coverage_correction_worklist,
)
from backend.app.datasets.phase5.export import init_private_dataset
from backend.app.datasets.phase5.hashes import sha256_file
from backend.app.datasets.phase5.ids import new_coverage_event_id
from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import manifest_path
from backend.app.datasets.phase5.schemas import CoverageEvent, DocumentRecord, SourceRecord


def _write_page(root: Path, *, page_id: str, seed: int = 0) -> None:
    pages = root / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (120, 120), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.point((seed % 100, (seed * 3) % 100), fill=(10, 20, 30))
    draw.rectangle([10, 10, 60, 40], outline=(0, 0, 0))
    img.save(pages / f"{page_id}.png")
    result = {
        "page_number": 1,
        "lines": [
            {
                "id": "line_000000",
                "bbox": {"x": 0.05, "y": 0.05, "width": 0.4, "height": 0.2},
                "polygon": {
                    "points": [
                        {"x": 0.05, "y": 0.05},
                        {"x": 0.45, "y": 0.05},
                        {"x": 0.45, "y": 0.25},
                        {"x": 0.05, "y": 0.25},
                    ]
                },
            }
        ],
        "words": [],
        "blocks": [
            {
                "id": "block_000000",
                "bbox": {"x": 0.05, "y": 0.05, "width": 0.4, "height": 0.2},
                "polygon": {
                    "points": [
                        {"x": 0.05, "y": 0.05},
                        {"x": 0.45, "y": 0.05},
                        {"x": 0.45, "y": 0.25},
                        {"x": 0.05, "y": 0.25},
                    ]
                },
                "line_ids": ["line_000000"],
            }
        ],
        "repair_regions": [],
    }
    (pages / f"{page_id}.result.json").write_text(json.dumps(result), encoding="utf-8")


def _seed_coverage_root(tmp_path: Path, *, pages: int = 3) -> Path:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    now = datetime.now(UTC)
    docs: list[DocumentRecord] = []
    sources: list[SourceRecord] = []
    for i in range(pages):
        page_id = f"page_{i:08d}_abcdef01"
        doc_id = f"doc_{i:08d}_abcdef01"
        group_id = f"grp_{i % 2:08d}_abcdef01"
        _write_page(root, page_id=page_id, seed=i)
        docs.append(
            DocumentRecord(
                document_id=doc_id,
                source_group_id=group_id,
                source_family="other",
                document_sha256=f"{i + 1:064x}",
                page_count=1,
                opaque_label=f"synth_{i}",
                source_relpath=f"synth_{i}.pdf",
                created_at=now,
            )
        )
        sources.append(
            SourceRecord(
                source_group_id=group_id,
                document_id=doc_id,
                page_id=page_id,
                page_index=0,
                page_width_px=120,
                page_height_px=120,
                page_relpath=f"pages/{page_id}.png",
                source_family="other",
                created_at=now,
            )
        )
    write_jsonl_atomic(manifest_path(root, "document-manifest.jsonl"), docs)
    write_jsonl_atomic(manifest_path(root, "source-manifest.jsonl"), sources)
    build_coverage_review(root)
    return root


def _resolve_event(
    root: Path,
    *,
    page_id: str,
    doc_id: str,
    outcome: str,
    reviewer: str = "cov_reviewer_01",
    supersedes: str | None = None,
) -> CoverageEvent:
    page_hash, overlay_hash = page_artefact_hashes(root, page_id)
    assert page_hash and overlay_hash
    event = CoverageEvent(
        coverage_event_id=new_coverage_event_id(),
        opaque_page_reference=page_id,
        opaque_document_reference=doc_id,
        reviewer_id=reviewer,
        action="resolve",
        outcome=outcome,
        page_render_hash=page_hash,
        overlay_hash=overlay_hash,
        supersedes_event_id=supersedes,
        created_at=datetime.now(UTC),
    )
    append_jsonl(manifest_path(root, "coverage-events.jsonl"), [event])
    return event


def test_coverage_event_rejects_script_label() -> None:
    with pytest.raises(ValueError):
        CoverageEvent(
            coverage_event_id="cov_abcdefghijklmn",
            opaque_page_reference="page_00000000_abcdef01",
            opaque_document_reference="doc_00000000_abcdef01",
            reviewer_id="cov_reviewer_01",
            action="resolve",
            outcome="handwritten",
            page_render_hash="a" * 64,
            overlay_hash="b" * 64,
            created_at=datetime.now(UTC),
        )


def test_coverage_event_append_only_supersession(tmp_path: Path) -> None:
    root = _seed_coverage_root(tmp_path, pages=2)
    page_id = "page_00000000_abcdef01"
    doc_id = "doc_00000000_abcdef01"
    first = _resolve_event(root, page_id=page_id, doc_id=doc_id, outcome="missing_region")
    page_hash, overlay_hash = page_artefact_hashes(root, page_id)
    reopen = CoverageEvent(
        coverage_event_id=new_coverage_event_id(),
        opaque_page_reference=page_id,
        opaque_document_reference=doc_id,
        reviewer_id="cov_reviewer_01",
        action="reopen",
        outcome=None,
        page_render_hash=page_hash or ("a" * 64),
        overlay_hash=overlay_hash or ("b" * 64),
        supersedes_event_id=first.coverage_event_id,
        created_at=datetime.now(UTC),
    )
    append_jsonl(manifest_path(root, "coverage-events.jsonl"), [reopen])
    second = _resolve_event(
        root,
        page_id=page_id,
        doc_id=doc_id,
        outcome="coverage_appears_complete",
        supersedes=reopen.coverage_event_id,
    )
    events = read_jsonl(manifest_path(root, "coverage-events.jsonl"), CoverageEvent)
    assert len(events) == 3
    state = current_coverage_state(root)
    assert page_id in state["current"]
    assert state["current"][page_id].coverage_event_id == second.coverage_event_id
    assert state["current"][page_id].outcome == "coverage_appears_complete"
    assert page_id in state["reopened_pages"]


def test_stale_hash_invalidates_resolution(tmp_path: Path) -> None:
    root = _seed_coverage_root(tmp_path, pages=1)
    page_id = "page_00000000_abcdef01"
    doc_id = "doc_00000000_abcdef01"
    _resolve_event(root, page_id=page_id, doc_id=doc_id, outcome="coverage_appears_complete")
    overlay = root / "coverage" / f"{page_id}.overlay.png"
    overlay.write_bytes(overlay.read_bytes() + b"\x00")
    state = current_coverage_state(root)
    assert page_id not in state["current"]
    assert page_id in state["stale_pages"]
    problems = verify_coverage_events(root)
    assert any("stale" in p for p in problems)


def test_correction_worklist_and_aggregate_privacy(tmp_path: Path) -> None:
    root = _seed_coverage_root(tmp_path, pages=3)
    pages = [
        ("page_00000000_abcdef01", "doc_00000000_abcdef01", "missing_region"),
        ("page_00000001_abcdef01", "doc_00000001_abcdef01", "coverage_appears_complete"),
        ("page_00000002_abcdef01", "doc_00000002_abcdef01", "crop_too_tight"),
    ]
    for page_id, doc_id, outcome in pages:
        _resolve_event(root, page_id=page_id, doc_id=doc_id, outcome=outcome)
    path, count = write_coverage_correction_worklist(root)
    assert count == 2
    text = path.read_text(encoding="utf-8")
    assert "missing_region" in text
    assert "crop_too_tight" in text
    assert '"coverage_appears_complete"' not in text
    aggregate = build_coverage_aggregate(root)
    md = render_coverage_aggregate_markdown(aggregate)
    assert "cov_reviewer_01" not in md
    assert "page_00000000" not in md
    assert "fixtures" not in md
    assert aggregate["missing_region"] == 1
    assert aggregate["crop_too_tight"] == 1
    assert aggregate["coverage_appears_complete"] == 1
    assert aggregate["review_completion_status"] == (
        "COVERAGE CORRECTION REQUIRED BEFORE ANNOTATION PILOT"
    )


def test_overlay_meta_has_hashes_and_no_forbidden_keys(tmp_path: Path) -> None:
    root = _seed_coverage_root(tmp_path, pages=1)
    problems = verify_coverage_artefacts(root)
    assert problems == []
    meta_files = list((root / "coverage").glob("*.meta.json"))
    assert meta_files
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert "page_render_hash" in meta
    assert "overlay_hash" in meta
    for key in meta:
        key_l = str(key).lower()
        assert "ocr" not in key_l
        assert "prediction" not in key_l
        assert "transcript" not in key_l
        assert "filename" not in key_l


def test_coverage_server_loopback_and_path_traversal(tmp_path: Path) -> None:
    root = _seed_coverage_root(tmp_path, pages=2)
    from scripts.phase5.coverage_server import make_handler

    handler = make_handler(root, expected_reviewer="cov_reviewer_01")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/next?reviewer=cov_reviewer_01")
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["opaque_page_reference"]
        assert "progress" in body
        assert body["progress"]["remaining"] == 2

        conn.request("GET", "/api/overlay/../etc/passwd")
        bad = conn.getresponse()
        bad.read()
        assert bad.status == 400

        conn.request("GET", "/api/next?reviewer=other")
        wrong = conn.getresponse()
        wrong_body = json.loads(wrong.read().decode("utf-8"))
        assert wrong.status == 400
        assert "error" in wrong_body

        conn.request("GET", "/")
        html_resp = conn.getresponse()
        html = html_resp.read().decode("utf-8")
        assert "indexedDB" not in html.lower()
        assert "serviceWorker" not in html
        assert "Do not use localStorage" in html

        page = body["opaque_page_reference"]
        doc = body["opaque_document_reference"]
        payload = json.dumps(
            {
                "opaque_page_reference": page,
                "opaque_document_reference": doc,
                "reviewer_id": "cov_reviewer_01",
                "action": "resolve",
                "outcome": "coverage_appears_complete",
            }
        )
        conn.request(
            "POST",
            "/api/coverage",
            body=payload,
            headers={"Content-Type": "application/json"},
        )
        post = conn.getresponse()
        post_body = json.loads(post.read().decode("utf-8"))
        assert post.status == 200
        assert post_body["ok"] is True
        events = read_jsonl(manifest_path(root, "coverage-events.jsonl"), CoverageEvent)
        assert len(events) == 1
        assert events[0].page_render_hash == sha256_file(root / "pages" / f"{page}.png")
    finally:
        server.shutdown()
