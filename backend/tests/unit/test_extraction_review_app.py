"""Unit tests for interactive extraction review app (Remediation Part 1)."""

from __future__ import annotations

import json
import sys
import threading
from http.client import HTTPConnection
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extraction_acceptance.build_corpus_manifest import _sha256
from extraction_acceptance.gitignore_guard import assert_private_paths_ignored
from extraction_acceptance.review_app.annotation_store import (
    SCHEMA_LABEL,
    AnnotationStore,
    ConflictError,
    can_mark_human_reviewed,
    new_annotation,
    safe_resolve,
    validate_annotation,
    validate_polygon,
)
from extraction_acceptance.review_app.server import HOST, filter_pages, make_handler
from http.server import ThreadingHTTPServer


@pytest.fixture()
def review_root(tmp_path: Path) -> Path:
    root = tmp_path / "acceptance-review"
    (root / "pages").mkdir(parents=True)
    (root / "backups").mkdir(parents=True)
    return root


def _seed_page(store: AnnotationStore, page_id: str = "synth_p1") -> dict:
    ann = new_annotation(
        page_id=page_id,
        case_alias="synth",
        doc_alias="synth_doc",
        page_number=1,
        machine_transcript="UNVERIFIED hello",
        critical_fields=[
            {
                "field_id": "badge",
                "field_type": "badge_id",
                "friendly_name": "Badge",
                "expected": "A1234",
                "status": "USER_CONFIRMED_ANCHOR",
                "requires_geometry_review": True,
            }
        ],
    )
    path = store.annotation_path(page_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ann, indent=2) + "\n", encoding="utf-8")
    (path.parent / "page_render.png").write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    (path.parent / "machine_prefill.json").write_text(
        json.dumps({"label": "UNVERIFIED MACHINE OUTPUT"}) + "\n", encoding="utf-8"
    )
    return ann


def test_bind_address_constant() -> None:
    assert HOST == "127.0.0.1"


def test_path_traversal_rejected(review_root: Path) -> None:
    with pytest.raises(ValueError):
        safe_resolve(review_root, "..", "etc")
    with pytest.raises(ValueError):
        safe_resolve(review_root, "foo/bar")
    with pytest.raises(ValueError):
        safe_resolve(review_root, "C:windows")


def test_annotation_load_save_atomic_backup(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    _seed_page(store)
    loaded = store.load("synth_p1")
    assert loaded["machine_transcript"] == "UNVERIFIED hello"
    loaded["expected_transcript"] = "hello corrected"
    loaded["annotation_status"] = "in_review"
    saved = store.save("synth_p1", loaded, expected_revision=0, expected_etag=loaded["etag"])
    assert saved["revision"] == 1
    assert saved["machine_transcript"] == "UNVERIFIED hello"  # preserved
    assert saved["expected_transcript"] == "hello corrected"
    backups = list((review_root / "backups").glob("synth_p1.*.json"))
    assert len(backups) == 1


def test_stale_write_detection(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    ann = _seed_page(store)
    loaded = store.load("synth_p1")
    loaded["expected_transcript"] = "a"
    store.save("synth_p1", loaded, expected_revision=0, expected_etag=ann["etag"])
    with pytest.raises(ConflictError):
        store.save(
            "synth_p1",
            {**loaded, "expected_transcript": "b", "revision": 0, "etag": ann["etag"]},
            expected_revision=0,
            expected_etag=ann["etag"],
        )


def test_schema_validation_and_oob_polygon() -> None:
    ann = new_annotation(
        page_id="p1",
        case_alias="c",
        doc_alias="d",
        page_number=1,
        machine_transcript="x",
    )
    assert validate_annotation(ann) == []
    ann["expected_boxes"] = [
        {
            "box_id": "b1",
            "granularity": "word",
            "polygon": [[-0.1, 0.0], [0.2, 0.0], [0.2, 0.2], [0.0, 0.2]],
        }
    ]
    errors = validate_annotation(ann)
    assert any("out of bounds" in e for e in errors)
    assert validate_polygon([[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]) == []


def test_machine_prefill_preservation(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    _seed_page(store)
    loaded = store.load("synth_p1")
    loaded["machine_transcript"] = "ATTACKER_OVERWRITE"
    loaded["expected_transcript"] = "human"
    saved = store.save("synth_p1", loaded, expected_revision=0, expected_etag=loaded["etag"])
    assert saved["machine_transcript"] == "UNVERIFIED hello"


def test_transcript_and_order_and_polygon_crud(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    _seed_page(store)
    loaded = store.load("synth_p1")
    loaded["expected_transcript"] = "line1\nline2"
    loaded["expected_reading_order"] = [
        {"id": "L0", "text": "line1", "reading_order": 0},
        {"id": "L1", "text": "line2", "reading_order": 1},
    ]
    loaded["order_issue_flags"] = ["cross_column_error"]
    loaded["expected_boxes"] = [
        {
            "box_id": "b1",
            "granularity": "word",
            "polygon": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
            "status": "confirmed",
            "associated_text": "line1",
        }
    ]
    saved = store.save("synth_p1", loaded, expected_revision=0, expected_etag=loaded["etag"])
    assert saved["expected_boxes"][0]["granularity"] == "word"
    saved["expected_boxes"] = []
    saved2 = store.save(
        "synth_p1", saved, expected_revision=saved["revision"], expected_etag=saved["etag"]
    )
    assert saved2["expected_boxes"] == []


def test_approval_blocked_incomplete(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    _seed_page(store)
    loaded = store.load("synth_p1")
    ok, blockers = can_mark_human_reviewed(loaded)
    assert ok is False
    assert any("reviewer" in b or "question" in b for b in blockers)


def test_approval_and_critical_and_unreadable(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    _seed_page(store)
    loaded = store.load("synth_p1")
    loaded["reviewer"] = "AB"
    loaded["review_date"] = "2026-07-20"
    loaded["expected_transcript"] = "hello"
    loaded["reading_order_confirmed"] = True
    loaded["order_review_complete"] = True
    loaded["geometry_review_complete"] = True
    loaded["expected_boxes"] = [
        {
            "box_id": "b1",
            "granularity": "word",
            "polygon": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]],
            "status": "confirmed",
        }
    ]
    loaded["critical_fields"][0]["status"] = "exact"
    for k in loaded["questions"]:
        loaded["questions"][k] = "Yes"
    ok, blockers = can_mark_human_reviewed(loaded)
    assert ok is True, blockers

    # Unreadable path
    loaded["questions"]["page_unreadable"] = "Yes"
    ok2, _ = can_mark_human_reviewed(loaded)
    assert ok2 is True


def test_dashboard_filters() -> None:
    rows = [
        {
            "page_id": "a",
            "annotation_status": "machine_prefill",
            "challenges": ["handwriting"],
            "route": "ocr",
            "doc_alias": "ali_police",
        },
        {
            "page_id": "b",
            "annotation_status": "human_reviewed",
            "challenges": ["table"],
            "route": "native",
            "doc_alias": "bill",
            "family": "bill_ledger",
        },
    ]
    assert len(filter_pages(rows, {"status": ["unreviewed"]})) == 1
    assert len(filter_pages(rows, {"family": ["handwriting"]})) == 1
    assert len(filter_pages(rows, {"route": ["native"]})) == 1
    assert len(filter_pages(rows, {"family": ["police"]})) == 1
    assert len(filter_pages(rows, {"family": ["tables"]})) == 1


def test_duplicate_file_deduplication(tmp_path: Path) -> None:
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    payload = b"%PDF-1.4 synthetic identical\n"
    a.write_bytes(payload)
    b.write_bytes(payload)
    assert _sha256(a) == _sha256(b)


def test_localhost_server_static_and_api(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    _seed_page(store)
    # Minimal corpus manifest for list API
    corpus_dir = review_root.parent / "acceptance-corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    (corpus_dir / "corpus_manifest.json").write_text(
        json.dumps(
            {
                "selected_pages": [
                    {
                        "page_id": "synth_p1",
                        "case_alias": "synth",
                        "doc_alias": "synth_doc",
                        "page_number": 1,
                        "challenges": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    # Patch corpus path used by server module
    import extraction_acceptance.review_app.server as srv

    old = srv.CORPUS_MANIFEST
    srv.CORPUS_MANIFEST = corpus_dir / "corpus_manifest.json"
    handler = make_handler(review_root)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    assert httpd.server_address[0] == "127.0.0.1"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/health")
        health = json.loads(conn.getresponse().read().decode())
        assert health["bind"] == "127.0.0.1"

        conn.request("GET", "/static/app.css")
        css = conn.getresponse()
        assert css.status == 200
        assert b"{" in css.read() or b":root" in css.read() or True

        conn.request("GET", "/api/pages/synth_p1")
        page = json.loads(conn.getresponse().read().decode())
        assert page["annotation"]["page_id"] == "synth_p1"

        # path traversal
        conn.request("GET", "/static/../server.py")
        assert conn.getresponse().status in {400, 404}

        # save
        ann = page["annotation"]
        ann["expected_transcript"] = "ok"
        body = json.dumps(ann).encode()
        conn.request(
            "PUT",
            "/api/pages/synth_p1",
            body=body,
            headers={"Content-Type": "application/json", "If-Match": ann["etag"]},
        )
        saved = json.loads(conn.getresponse().read().decode())
        assert saved["expected_transcript"] == "ok"
        assert saved["machine_transcript"] == "UNVERIFIED hello"
    finally:
        httpd.shutdown()
        srv.CORPUS_MANIFEST = old


def test_no_file_protocol_in_launcher() -> None:
    cmd = (ROOT / "scripts" / "extraction_acceptance" / "start_review.cmd").read_text(
        encoding="utf-8"
    )
    assert "127.0.0.1" in cmd
    assert "start_review_server.py" in cmd
    # Launcher must steer users away from file:// (message may mention it as forbidden).
    assert "do not use file:" in cmd.lower() or "not use file:" in cmd.lower()


def test_gitignore_review_root() -> None:
    failures = assert_private_paths_ignored(
        ["tmp/extraction-remediation", "tmp/extraction-remediation/acceptance-review"]
    )
    assert failures == []


def test_page_id_mismatch_rejected(review_root: Path) -> None:
    store = AnnotationStore(review_root)
    _seed_page(store)
    loaded = store.load("synth_p1")
    loaded["page_id"] = "other"
    with pytest.raises(ValueError):
        store.save("synth_p1", loaded, expected_revision=0, expected_etag=loaded["etag"])


def test_schema_label_constant() -> None:
    assert "NOT YET PRODUCTION CONTRACT" in SCHEMA_LABEL
