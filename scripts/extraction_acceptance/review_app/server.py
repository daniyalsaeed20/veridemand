"""Localhost-only extraction annotation server (127.0.0.1).

EVALUATION TOOLING — NOT PRODUCTION UI.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from extraction_acceptance.review_app.annotation_store import (  # noqa: E402
    AnnotationStore,
    ConflictError,
    can_mark_human_reviewed,
    safe_resolve,
    validate_page_id,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_REVIEW_ROOT = ROOT / "tmp" / "extraction-remediation" / "acceptance-review"
CORPUS_MANIFEST = ROOT / "tmp" / "extraction-remediation" / "acceptance-corpus" / "corpus_manifest.json"

HOST = "127.0.0.1"
DEFAULT_PORT = 8765

logger = logging.getLogger("extraction_review")
# Never log transcript/critical values
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

PAGE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
OVERLAY_FILES = {
    "native_words": "native_words.json",
    "native_lines": "native_lines.json",
    "ocr_lines": "ocr_lines.json",
    "source_tokens": "source_tokens.json",
    "source_spans": "source_spans.json",
    "machine_prefill": "machine_prefill.json",
}


def _load_corpus_pages() -> list[dict]:
    if not CORPUS_MANIFEST.is_file():
        return []
    data = json.loads(CORPUS_MANIFEST.read_text(encoding="utf-8"))
    return list(data.get("selected_pages") or [])


def filter_pages(rows: list[dict], filters: dict[str, list[str]]) -> list[dict]:
    """Apply dashboard filters (also used by tests)."""
    out = rows
    status = filters.get("status", [""])[0]
    if status:
        if status == "unreviewed":
            out = [r for r in out if r.get("annotation_status") in {"machine_prefill", ""}]
        else:
            out = [r for r in out if r.get("annotation_status") == status]
    challenge = filters.get("challenge", [""])[0]
    if challenge:
        out = [r for r in out if challenge in (r.get("challenges") or [])]
    route = filters.get("route", [""])[0]
    if route == "native":
        out = [r for r in out if r.get("route") == "native"]
    elif route == "ocr":
        out = [r for r in out if r.get("route") == "ocr"]
    family = filters.get("family", [""])[0]
    if family == "police":
        out = [r for r in out if "police" in str(r.get("doc_alias") or "") or "police" in (r.get("challenges") or [])]
    if family == "handwriting":
        out = [r for r in out if "handwriting" in (r.get("challenges") or [])]
    if family == "corrupt_hidden_ocr":
        out = [r for r in out if "corrupt_hidden_ocr" in (r.get("challenges") or [])]
    if family == "tables":
        out = [r for r in out if "table" in (r.get("challenges") or []) or r.get("family") == "bill_ledger"]
    return out


def make_handler(review_root: Path) -> type[BaseHTTPRequestHandler]:
    store = AnnotationStore(review_root)

    class Handler(BaseHTTPRequestHandler):
        server_version = "VeriDemandExtractionReview/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            # Avoid logging query bodies / private content
            logger.info("%s %s", self.command, self.path.split("?", 1)[0])

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: Any) -> None:
            data = json.dumps(obj).encode("utf-8")
            self._send(code, data, "application/json; charset=utf-8")

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path in ("/", "/index.html"):
                return self._serve_static("index.html")
            if path == "/page.html":
                return self._serve_static("page.html")
            if path.startswith("/static/"):
                name = path[len("/static/") :]
                return self._serve_static(name)

            if path == "/api/health":
                return self._json(200, {"ok": True, "bind": HOST})

            if path == "/api/pages":
                return self._api_list_pages(qs)

            m = re.match(r"^/api/pages/([A-Za-z0-9_\-]+)$", path)
            if m:
                return self._api_get_page(m.group(1))

            m = re.match(r"^/api/pages/([A-Za-z0-9_\-]+)/render$", path)
            if m:
                return self._api_render(m.group(1))

            m = re.match(r"^/api/pages/([A-Za-z0-9_\-]+)/overlays/([A-Za-z0-9_\-]+)$", path)
            if m:
                return self._api_overlay(m.group(1), m.group(2))

            self._json(404, {"error": "not_found"})

        def do_PUT(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            m = re.match(r"^/api/pages/([A-Za-z0-9_\-]+)$", parsed.path)
            if not m:
                return self._json(404, {"error": "not_found"})
            page_id = m.group(1)
            try:
                validate_page_id(page_id)
                payload = self._read_json()
                etag = self.headers.get("If-Match") or payload.get("etag")
                rev = payload.get("revision")
                saved = store.save(
                    page_id,
                    payload,
                    expected_etag=etag,
                    expected_revision=rev if isinstance(rev, int) else None,
                )
                logger.info("saved page_id=%s status=%s rev=%s", page_id, saved.get("annotation_status"), saved.get("revision"))
                return self._json(200, saved)
            except ConflictError as exc:
                return self._json(409, {"error": "conflict", "detail": str(exc)})
            except FileNotFoundError:
                return self._json(404, {"error": "not_found"})
            except ValueError as exc:
                return self._json(400, {"error": "validation", "detail": str(exc)})
            except Exception as exc:  # noqa: BLE001
                logger.info("save_error page_id=%s type=%s", page_id, type(exc).__name__)
                return self._json(500, {"error": "server_error"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            m = re.match(r"^/api/pages/([A-Za-z0-9_\-]+)/mark-reviewed$", parsed.path)
            if not m:
                return self._json(404, {"error": "not_found"})
            page_id = m.group(1)
            try:
                data = store.load(page_id)
                body = self._read_json()
                # Merge optional fields from body
                for key in ("reviewer", "review_date", "notes", "questions", "expected_transcript",
                            "expected_reading_order", "expected_boxes", "critical_fields",
                            "reading_order_confirmed", "order_issue_flags",
                            "geometry_review_complete", "text_review_complete", "order_review_complete",
                            "ground_truth_ready"):
                    if key in body:
                        data[key] = body[key]
                ok, blockers = can_mark_human_reviewed(data)
                if not ok:
                    return self._json(400, {"error": "incomplete", "blockers": blockers})
                data["annotation_status"] = "human_reviewed"
                if body.get("needs_second_review"):
                    data["annotation_status"] = "needs_second_review"
                if data.get("questions", {}).get("page_unreadable") == "Yes":
                    data["annotation_status"] = "unreadable"
                saved = store.save(
                    page_id,
                    data,
                    expected_etag=data.get("etag"),
                    expected_revision=data.get("revision"),
                )
                logger.info("marked page_id=%s status=%s", page_id, saved.get("annotation_status"))
                return self._json(200, saved)
            except ConflictError as exc:
                return self._json(409, {"error": "conflict", "detail": str(exc)})
            except FileNotFoundError:
                return self._json(404, {"error": "not_found"})
            except ValueError as exc:
                return self._json(400, {"error": "validation", "detail": str(exc)})

        def _serve_static(self, name: str) -> None:
            if ".." in name or name.startswith("/") or "\\" in name:
                return self._json(400, {"error": "bad_path"})
            path = (STATIC_DIR / name).resolve()
            try:
                path.relative_to(STATIC_DIR.resolve())
            except ValueError:
                return self._json(400, {"error": "bad_path"})
            if not path.is_file():
                return self._json(404, {"error": "not_found"})
            data = path.read_bytes()
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self._send(200, data, ctype)

        def _api_list_pages(self, qs: dict) -> None:
            corpus_pages = _load_corpus_pages()
            rows = []
            for cp in corpus_pages:
                page_id = cp["page_id"]
                meta = {}
                meta_path = store.pages_dir / page_id / "page_meta.json"
                if meta_path.is_file():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                ann = {}
                ann_path = store.pages_dir / page_id / "annotation.json"
                if ann_path.is_file():
                    ann = json.loads(ann_path.read_text(encoding="utf-8"))
                crit = ann.get("critical_fields") or cp.get("critical_anchors") or []
                crit_status = "none"
                if crit:
                    unresolved = [
                        c
                        for c in crit
                        if c.get("status") not in {"exact", "incorrect", "unreadable"}
                        and c.get("match_status") not in {"exact", "incorrect", "unreadable"}
                    ]
                    crit_status = "unresolved" if unresolved else "resolved"
                rows.append(
                    {
                        "page_id": page_id,
                        "case_alias": cp.get("case_alias") or ann.get("case_alias"),
                        "doc_alias": cp.get("doc_alias") or ann.get("doc_alias"),
                        "family": cp.get("family"),
                        "page_number": cp.get("page_number"),
                        "challenges": cp.get("challenges") or ann.get("challenges") or [],
                        "annotation_status": ann.get("annotation_status") or "machine_prefill",
                        "route": meta.get("route"),
                        "has_native": meta.get("has_native"),
                        "has_ocr": meta.get("has_ocr"),
                        "has_render": meta.get("has_render"),
                        "critical_anchor_status": crit_status,
                        "text_review_complete": bool(ann.get("text_review_complete")),
                        "order_review_complete": bool(ann.get("order_review_complete")),
                        "geometry_review_complete": bool(ann.get("geometry_review_complete")),
                        "selection_reason": cp.get("selection_reason"),
                    }
                )
            filtered = filter_pages(rows, qs)
            self._json(200, {"pages": filtered, "count": len(filtered)})

        def _api_get_page(self, page_id: str) -> None:
            try:
                validate_page_id(page_id)
                ann = store.load(page_id)
                meta_path = store.page_dir(page_id) / "page_meta.json"
                meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
                prefill_path = store.page_dir(page_id) / "machine_prefill.json"
                prefill = (
                    json.loads(prefill_path.read_text(encoding="utf-8")) if prefill_path.is_file() else {}
                )
                # Neighbor ids for nav
                ids = [p["page_id"] for p in _load_corpus_pages()]
                idx = ids.index(page_id) if page_id in ids else -1
                self._json(
                    200,
                    {
                        "annotation": ann,
                        "meta": meta,
                        "prefill": {
                            "label": prefill.get("label"),
                            "native_route": (prefill.get("native") or {}).get("route"),
                            "has_ocr": bool(prefill.get("ocr")),
                            "layers_separate": True,
                        },
                        "nav": {
                            "prev": ids[idx - 1] if idx > 0 else None,
                            "next": ids[idx + 1] if 0 <= idx < len(ids) - 1 else None,
                            "index": idx,
                            "total": len(ids),
                        },
                    },
                )
            except FileNotFoundError:
                self._json(404, {"error": "not_found"})
            except ValueError as exc:
                self._json(400, {"error": "validation", "detail": str(exc)})

        def _api_render(self, page_id: str) -> None:
            try:
                validate_page_id(page_id)
                path = safe_resolve(store.pages_dir, page_id, "page_render.png")
                # safe_resolve with two parts - need to fix for nested
                path = (store.page_dir(page_id) / "page_render.png").resolve()
                path.relative_to(store.root)
                if not path.is_file():
                    return self._json(404, {"error": "no_render"})
                data = path.read_bytes()
                self._send(200, data, "image/png")
            except ValueError:
                self._json(400, {"error": "bad_path"})

        def _api_overlay(self, page_id: str, layer: str) -> None:
            try:
                validate_page_id(page_id)
                if layer not in OVERLAY_FILES:
                    return self._json(404, {"error": "unknown_layer"})
                path = store.page_dir(page_id) / OVERLAY_FILES[layer]
                path = path.resolve()
                path.relative_to(store.root)
                if not path.is_file():
                    return self._json(200, {"label": "UNVERIFIED MACHINE OUTPUT", "items": []})
                data = json.loads(path.read_text(encoding="utf-8"))
                self._json(200, data)
            except ValueError:
                self._json(400, {"error": "bad_path"})

    return Handler


def run_server(*, host: str = HOST, port: int = DEFAULT_PORT, review_root: Path | None = None, open_browser: bool = True) -> None:
    if host != "127.0.0.1":
        raise SystemExit("Refusing to bind to non-localhost address")
    root = (review_root or DEFAULT_REVIEW_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    handler = make_handler(root)
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"Extraction review server listening on {url}")
    print("Bind: 127.0.0.1 only. Ctrl+C to stop.")
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_server()
