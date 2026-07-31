#!/usr/bin/env python3
"""Loopback-only Phase 5 page coverage reviewer (127.0.0.1).

Separate from script labelling. Shows page overlays only — no OCR text,
filenames, candidate provenance, or script labels. Does not fabricate events.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Phase 5 coverage review (loopback)</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 1100px; }
  #overlay { max-width: 100%; border: 1px solid #ccc; background: #f7f7f7; }
  .meta { color: #444; font-size: 0.9rem; }
  button { margin: 0.25rem; }
</style>
</head>
<body>
<h1>Phase 5 page coverage review</h1>
<p class="meta">Loopback only. Coverage decisions are not script labels.
No OCR text or source filenames are shown.</p>
<p id="status" class="meta">Loading…</p>
<img id="overlay" alt="page overlay"/>
<div id="actions"></div>
<script>
const reviewer = new URLSearchParams(location.search).get('reviewer') || 'rev_coverage';
const outcomes = [
  'coverage_appears_complete','missing_region','crop_too_tight','crop_too_broad',
  'duplicate_only','page_requires_manual_review','page_not_reviewable'
];
let current = null;

async function loadNext() {
  const r = await fetch('/api/next');
  const data = await r.json();
  const status = document.getElementById('status');
  const img = document.getElementById('overlay');
  const actions = document.getElementById('actions');
  actions.innerHTML = '';
  if (!data.opaque_page_reference) {
    status.textContent = data.message || 'Coverage queue empty';
    img.removeAttribute('src');
    current = null;
    return;
  }
  current = data;
  status.textContent = 'page=' + data.opaque_page_reference +
    ' · doc=' + data.opaque_document_reference +
    ' · crops=' + data.crop_count +
    ' · remaining≈' + (data.remaining ?? '?');
  img.src = '/api/overlay/' + encodeURIComponent(data.opaque_page_reference);
  for (const outcome of outcomes) {
    const b = document.createElement('button');
    b.textContent = outcome;
    b.onclick = () => submit(outcome);
    actions.appendChild(b);
  }
}

async function submit(outcome) {
  if (!current) return;
  const body = {
    opaque_page_reference: current.opaque_page_reference,
    opaque_document_reference: current.opaque_document_reference,
    reviewer_id: reviewer,
    outcome: outcome,
  };
  const r = await fetch('/api/coverage', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    document.getElementById('status').textContent = 'Error: ' + await r.text();
    return;
  }
  await loadNext();
}
loadNext();
</script>
</body>
</html>
"""


def _ensure_repo_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def make_handler(private_root: Path) -> type[BaseHTTPRequestHandler]:
    _ensure_repo_path()
    from backend.app.datasets.phase5.coverage import coverage_dir
    from backend.app.datasets.phase5.ids import new_coverage_event_id
    from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl
    from backend.app.datasets.phase5.paths import manifest_path
    from backend.app.datasets.phase5.schemas import CoverageEvent, CoverageQueueManifest

    queue_path = manifest_path(private_root, "coverage-queue.jsonl")
    events_path = manifest_path(private_root, "coverage-events.jsonl")
    cov_root = coverage_dir(private_root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("coverage: " + (fmt % args) + "\n")

        def _json(self, code: int, payload: object) -> None:
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def _html(self, code: int, body: str) -> None:
            raw = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._html(200, HTML_PAGE)
                return
            if parsed.path == "/api/next":
                queues = read_jsonl(queue_path, CoverageQueueManifest)
                if not queues:
                    self._json(200, {"opaque_page_reference": None, "message": "No coverage queue"})
                    return
                queue = queues[-1]
                events = read_jsonl(events_path, CoverageEvent)
                done = {e.opaque_page_reference for e in events}
                remaining = [e for e in queue.entries if e.opaque_page_reference not in done]
                if not remaining:
                    self._json(
                        200, {"opaque_page_reference": None, "message": "Coverage queue empty"}
                    )
                    return
                entry = remaining[0]
                self._json(
                    200,
                    {
                        "opaque_page_reference": entry.opaque_page_reference,
                        "opaque_document_reference": entry.opaque_document_reference,
                        "crop_count": entry.crop_count,
                        "remaining": len(remaining),
                    },
                )
                return
            if parsed.path.startswith("/api/overlay/"):
                page_ref = parsed.path[len("/api/overlay/") :]
                if "/" in page_ref or ".." in page_ref:
                    self.send_error(400, "bad page ref")
                    return
                path = (cov_root / f"{page_ref}.overlay.png").resolve()
                if not str(path).startswith(str(cov_root.resolve())):
                    self.send_error(400, "path rejected")
                    return
                if not path.is_file():
                    self.send_error(404, "overlay missing")
                    return
                data = path.read_bytes()
                ctype = mimetypes.guess_type(path.name)[0] or "image/png"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_error(404, "not found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/coverage":
                self.send_error(404, "not found")
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(400, {"error": "invalid json"})
                return
            try:
                event = CoverageEvent(
                    coverage_event_id=new_coverage_event_id(),
                    opaque_page_reference=str(body["opaque_page_reference"]),
                    opaque_document_reference=str(body["opaque_document_reference"]),
                    reviewer_id=str(body["reviewer_id"]),
                    outcome=str(body["outcome"]),
                    note=body.get("note"),
                    created_at=datetime.now(UTC),
                )
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            append_jsonl(events_path, [event])
            self._json(200, {"ok": True, "coverage_event_id": event.coverage_event_id})

    return Handler


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_path()
    from backend.app.datasets.phase5.paths import default_private_root

    parser = argparse.ArgumentParser(description="Phase 5 loopback coverage reviewer")
    parser.add_argument("--root", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing non-loopback bind", file=sys.stderr)
        return 2
    private_root = Path(args.root) if args.root else default_private_root()
    if not private_root.is_dir():
        print(f"Private root missing: {private_root}", file=sys.stderr)
        return 1
    handler = make_handler(private_root)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Phase 5 coverage review on http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
