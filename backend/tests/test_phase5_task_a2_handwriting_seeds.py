"""Phase 5 Task A2 handwriting seed queue, collection, and privacy tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from backend.app.contracts.geometry import NormalisedBoundingBox
from backend.app.datasets.phase5.export import export_crop_from_page, init_private_dataset
from backend.app.datasets.phase5.handwriting_seeds import (
    build_handwriting_seed_aggregate,
    build_handwriting_seed_queue,
    close_page,
    confirm_drawn_region,
    geometry_warnings,
    render_handwriting_seed_readiness_markdown,
    resolve_exact_duplicates,
    reviewer_id_ok,
    select_existing_crop,
    verify_handwriting_seeds,
)
from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl, write_jsonl_atomic
from backend.app.datasets.phase5.paths import manifest_path, pages_dir
from backend.app.datasets.phase5.schemas import (
    CropRecord,
    DocumentRecord,
    HandwritingSeedEvent,
    HandwritingSeedQueueManifest,
    HandwritingSeedRecord,
    ResolvedLabelRecord,
    ReviewQueueEntry,
    ReviewQueueManifest,
    SourceRecord,
)
from backend.app.main import app

ROOT = Path(__file__).resolve().parents[2]


def _now() -> datetime:
    return datetime.now(UTC)


def _write_page(root: Path, *, page_id: str, seed: int = 0) -> None:
    pages = pages_dir(root)
    pages.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (200, 200), color=(245, 245, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20 + seed, 20, 80 + seed, 50], outline=(0, 0, 0), fill=(30, 30, 30))
    img.save(pages / f"{page_id}.png")


def _seed_root(tmp_path: Path) -> Path:
    root = tmp_path / "phase5"
    init_private_dataset(root)
    docs = [
        DocumentRecord(
            document_id="doc_aaaa1111",
            source_group_id="srcgrp_aaaa1111",
            source_family="police_form",
            document_sha256="a" * 64,
            page_count=2,
            opaque_label="synthetic_police",
            source_relpath="sources/doc_aaaa1111.pdf",
            created_at=_now(),
        ),
        DocumentRecord(
            document_id="doc_bbbb2222",
            source_group_id="srcgrp_bbbb2222",
            source_family="billing_ledger",
            document_sha256="b" * 64,
            page_count=1,
            opaque_label="synthetic_billing",
            source_relpath="sources/doc_bbbb2222.pdf",
            created_at=_now(),
        ),
        DocumentRecord(
            document_id="doc_cccc3333",
            source_group_id="srcgrp_cccc3333",
            source_family="medical_form",
            document_sha256="c" * 64,
            page_count=1,
            opaque_label="synthetic_medical",
            source_relpath="sources/doc_cccc3333.pdf",
            created_at=_now(),
        ),
    ]
    append_jsonl(manifest_path(root, "document-manifest.jsonl"), docs)
    sources = [
        SourceRecord(
            source_group_id="srcgrp_aaaa1111",
            document_id="doc_aaaa1111",
            page_id="page_police01",
            page_index=0,
            page_width_px=200,
            page_height_px=200,
            page_relpath="pages/page_police01.png",
            source_family="police_form",
            created_at=_now(),
        ),
        SourceRecord(
            source_group_id="srcgrp_aaaa1111",
            document_id="doc_aaaa1111",
            page_id="page_police02",
            page_index=1,
            page_width_px=200,
            page_height_px=200,
            page_relpath="pages/page_police02.png",
            source_family="police_form",
            created_at=_now(),
        ),
        SourceRecord(
            source_group_id="srcgrp_bbbb2222",
            document_id="doc_bbbb2222",
            page_id="page_billing1",
            page_index=0,
            page_width_px=200,
            page_height_px=200,
            page_relpath="pages/page_billing1.png",
            source_family="billing_ledger",
            created_at=_now(),
        ),
        SourceRecord(
            source_group_id="srcgrp_cccc3333",
            document_id="doc_cccc3333",
            page_id="page_medical1",
            page_index=0,
            page_width_px=200,
            page_height_px=200,
            page_relpath="pages/page_medical1.png",
            source_family="medical_form",
            created_at=_now(),
        ),
    ]
    append_jsonl(manifest_path(root, "source-manifest.jsonl"), sources)
    for page_id, seed in (
        ("page_police01", 0),
        ("page_police02", 1),
        ("page_billing1", 2),
        ("page_medical1", 3),
    ):
        _write_page(root, page_id=page_id, seed=seed)

    # Create one crop on medical page and mark it uncertain via prototype queue + resolve.
    with Image.open(pages_dir(root) / "page_medical1.png") as img:
        page = img.convert("RGB")
        crop = export_crop_from_page(
            private_root=root,
            page_image=page,
            source_bbox=NormalisedBoundingBox(x=0.1, y=0.1, width=0.3, height=0.2),
            source_polygon=None,
            candidate_source="full_page_ocr",
            source_group_id="srcgrp_cccc3333",
            document_id="doc_cccc3333",
            page_id="page_medical1",
            page_index=0,
            existing_by_key={},
        )
    assert crop is not None
    append_jsonl(manifest_path(root, "crop-manifest.jsonl"), [crop])
    append_jsonl(
        manifest_path(root, "resolved-labels.jsonl"),
        [
            ResolvedLabelRecord(
                crop_id=crop.crop_id,
                crop_sha256=crop.sha256,
                status="single_review",
                label="uncertain",
                training_eligible=False,
                prototype_model_eligible=False,
                primary_label="uncertain",
                source_group_id="srcgrp_cccc3333",
                resolved_at=_now(),
            )
        ],
    )
    write_jsonl_atomic(
        manifest_path(root, "prototype-primary-queue.jsonl"),
        [
            ReviewQueueManifest(
                queue_version="phase5-prototype-primary-v1",
                queue_algorithm_version="phase5-primary-queue-v1",
                queue_name="prototype-primary",
                authorised_for_review=True,
                created_at=_now(),
                seed=4101,
                content_sha256="d" * 64,
                entries=[
                    ReviewQueueEntry(crop_id=crop.crop_id, crop_sha256=crop.sha256, queue_index=0)
                ],
            )
        ],
    )
    # Coverage worklist page (police02).
    worklist = root / "reports" / "coverage-correction-worklist.jsonl"
    worklist.parent.mkdir(parents=True, exist_ok=True)
    worklist.write_text(
        json.dumps(
            {
                "worklist_version": "phase5-coverage-worklist-v1",
                "opaque_page_reference": "page_police02",
                "opaque_document_reference": "doc_aaaa1111",
                "coverage_outcome": "missing_region",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def test_reviewer_id_validation() -> None:
    assert reviewer_id_ok("handwriting_reviewer_01")
    assert not reviewer_id_ok("proto_reviewer_01")
    assert not reviewer_id_ok("rev_abc")
    assert not reviewer_id_ok("")


def test_geometry_warnings_and_validation() -> None:
    small = NormalisedBoundingBox(x=0.1, y=0.1, width=0.005, height=0.005)
    assert "unusually_small_region" in geometry_warnings(small)
    broad = NormalisedBoundingBox(x=0.05, y=0.05, width=0.9, height=0.9)
    assert "unusually_broad_region" in geometry_warnings(broad)
    with pytest.raises(ValueError):
        NormalisedBoundingBox(x=0.5, y=0.5, width=0.0, height=0.1)
    with pytest.raises(ValueError):
        NormalisedBoundingBox(x=0.9, y=0.1, width=0.2, height=0.1)


def test_targeted_queue_determinism_and_priorities(tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    a = build_handwriting_seed_queue(root)
    b = build_handwriting_seed_queue(root)
    assert a["content_sha256"] == b["content_sha256"]
    assert a["page_count"] == b["page_count"]
    assert a["page_count"] >= 3  # police pages + uncertain medical; billing excluded
    assert a["uncertain_source_page_count"] >= 1
    assert a["coverage_worklist_page_count"] >= 1
    assert a["police_form_page_count"] >= 1
    # Billing-only page must not appear without uncertain/coverage reason.
    queues = read_jsonl(
        manifest_path(root, "handwriting-seed-queue.jsonl"),
        HandwritingSeedQueueManifest,
    )
    pages = {e.opaque_page_reference for e in queues[-1].entries}
    assert "page_billing1" not in pages
    assert "page_medical1" in pages
    assert "page_police01" in pages


def test_manual_region_creation_and_select_existing(tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    build_handwriting_seed_queue(root)
    crops_before = read_jsonl(manifest_path(root, "crop-manifest.jsonl"), CropRecord)
    existing = crops_before[0]
    result = confirm_drawn_region(
        private_root=root,
        opaque_page_reference="page_police01",
        opaque_document_reference="doc_aaaa1111",
        source_group_id="srcgrp_aaaa1111",
        reviewer_id="handwriting_reviewer_01",
        bbox={"x": 0.2, "y": 0.2, "width": 0.25, "height": 0.15},
        categories=["hand_printed", "digits"],
    )
    assert result["ok"] is True
    assert result["action"] == "confirm_region"
    selected = select_existing_crop(
        private_root=root,
        opaque_page_reference="page_medical1",
        opaque_document_reference="doc_cccc3333",
        source_group_id="srcgrp_cccc3333",
        reviewer_id="handwriting_reviewer_01",
        parent_crop_id=existing.crop_id,
        categories=["cursive"],
    )
    assert selected["ok"] is True
    # Prior uncertain resolved label must remain unchanged.
    resolved = read_jsonl(manifest_path(root, "resolved-labels.jsonl"), ResolvedLabelRecord)
    assert resolved[0].label == "uncertain"
    problems = verify_handwriting_seeds(root)
    assert problems == []
    # Crop generation determinism: same geometry resume should not explode.
    again = confirm_drawn_region(
        private_root=root,
        opaque_page_reference="page_police01",
        opaque_document_reference="doc_aaaa1111",
        source_group_id="srcgrp_aaaa1111",
        reviewer_id="handwriting_reviewer_01",
        bbox={"x": 0.2, "y": 0.2, "width": 0.25, "height": 0.15},
    )
    assert again["ok"] is True
    dup = resolve_exact_duplicates(root)
    assert dup["exact_duplicates"] >= 1
    assert dup["canonical_active"] >= 1


def test_append_only_events_and_close_page(tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    build_handwriting_seed_queue(root)
    confirm_drawn_region(
        private_root=root,
        opaque_page_reference="page_police01",
        opaque_document_reference="doc_aaaa1111",
        source_group_id="srcgrp_aaaa1111",
        reviewer_id="handwriting_reviewer_01",
        bbox={"x": 0.15, "y": 0.15, "width": 0.2, "height": 0.1},
    )
    close_page(
        private_root=root,
        opaque_page_reference="page_police02",
        opaque_document_reference="doc_aaaa1111",
        source_group_id="srcgrp_aaaa1111",
        reviewer_id="handwriting_reviewer_01",
        action="no_usable_handwriting",
    )
    events = read_jsonl(manifest_path(root, "handwriting-seed-events.jsonl"), HandwritingSeedEvent)
    assert len(events) == 2
    assert events[0].action == "confirm_region"
    assert events[1].action == "no_usable_handwriting"


def test_no_visible_text_fields_on_seed_schema() -> None:
    with pytest.raises(ValidationError):
        HandwritingSeedRecord.model_validate(
            {
                "seed_region_id": "hwseed_abcdefgh",
                "opaque_document_id": "doc_abcdefgh",
                "opaque_page_reference": "page_abcdefgh",
                "source_group_id": "srcgrp_abcdefgh",
                "reviewer_id": "handwriting_reviewer_01",
                "geometry_normalized": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "page_render_sha256": "a" * 64,
                "crop_sha256": "b" * 64,
                "perceptual_hash": "0123456789abcdef",
                "source_reference": "manual_draw:x",
                "crop_id": "crop_abcdefgh",
                "created_at": _now().isoformat(),
                "text": "leaked",
            }
        )


def test_aggregate_report_privacy(tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    build_handwriting_seed_queue(root)
    confirm_drawn_region(
        private_root=root,
        opaque_page_reference="page_police01",
        opaque_document_reference="doc_aaaa1111",
        source_group_id="srcgrp_aaaa1111",
        reviewer_id="handwriting_reviewer_01",
        bbox={"x": 0.12, "y": 0.12, "width": 0.2, "height": 0.12},
        categories=["signature"],
    )
    report = build_handwriting_seed_aggregate(root)
    md = render_handwriting_seed_readiness_markdown(report)
    assert "page_police01" not in md
    assert "srcgrp_" not in md
    assert "handwriting_reviewer_01" not in md
    assert "leaked" not in md
    assert "crop_" not in md
    assert report["regions_created_or_selected"] == 1
    assert "readiness" in report


def test_seed_server_loopback_and_path_traversal(tmp_path: Path) -> None:
    root = _seed_root(tmp_path)
    build_handwriting_seed_queue(root)
    from scripts.phase5.handwriting_seed_server import make_handler

    handler = make_handler(root, expected_reviewer="handwriting_reviewer_01")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/next?reviewer=handwriting_reviewer_01")
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        assert resp.status == 200
        assert body["opaque_page_reference"]
        assert "text" not in body
        assert "prediction" not in body
        page = body["opaque_page_reference"]
        conn.request("GET", f"/api/page/{page}")
        assert conn.getresponse().status == 200
        conn.request("GET", "/api/page/../secret.png")
        assert conn.getresponse().status == 400
        conn.request(
            "POST",
            "/api/seed",
            body=json.dumps(
                {
                    "reviewer_id": "handwriting_reviewer_01",
                    "action": "confirm_region",
                    "opaque_page_reference": page,
                    "opaque_document_reference": body["opaque_document_reference"],
                    "source_group_id": body["source_group_id"],
                    "bbox": {"x": 0.3, "y": 0.3, "width": 0.2, "height": 0.1},
                    "text": "nope",
                }
            ),
            headers={"Content-Type": "application/json"},
        )
        bad = conn.getresponse()
        assert bad.status == 400
        # HTML must not advertise browser persistence APIs.
        conn.request("GET", "/")
        html = conn.getresponse().read().decode("utf-8")
        assert "localStorage" in html  # mentioned as forbidden
        assert "Do not use localStorage" in html
        assert "indexedDB" not in html.lower().replace("indexeddb", "")
        assert "localStorage.setItem" not in html
        assert "serviceWorker" not in html
    finally:
        server.shutdown()


def test_handwriting_seed_server_not_in_fastapi() -> None:
    paths = {getattr(r, "path", None) for r in app.routes}
    assert not any(p and "handwriting" in p and "seed" in p for p in paths if isinstance(p, str))
    main_src = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    assert "handwriting_seed_server" not in main_src


def test_no_automatic_handwriting_decision_in_module() -> None:
    src = (ROOT / "backend" / "app" / "datasets" / "phase5" / "handwriting_seeds.py").read_text(
        encoding="utf-8"
    )
    assert "import paddle" not in src.lower()
    assert "onnxruntime" not in src.lower()
    assert "openai" not in src.lower()
    assert "HandwritingClassifier" not in src
    server = (ROOT / "scripts" / "phase5" / "handwriting_seed_server.py").read_text(
        encoding="utf-8"
    )
    assert "HandwritingClassifier" not in server
    assert "localStorage.setItem" not in server
    assert "classify(" not in server
    assert "No OCR" in server
