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
from urllib.parse import parse_qs, urlparse

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
  #actions button { display: block; }
</style>
</head>
<body>
<h1>Phase 5 page coverage review</h1>
<p class="meta">Loopback only. Coverage decisions are not script labels.
No OCR text or source filenames are shown. Do not use localStorage.</p>
<p id="status" class="meta">Loading…</p>
<img id="overlay" alt="page overlay"/>
<div id="actions"></div>
<script>
const reviewer = new URLSearchParams(location.search).get('reviewer') || '';
const outcomes = [
  'coverage_appears_complete','missing_region','crop_too_tight','crop_too_broad',
  'duplicate_only','page_requires_manual_review','page_not_reviewable'
];
let current = null;

function progressText(p) {
  if (!p) return '';
  return 'completed=' + (p.completed ?? 0) +
    ' · remaining=' + (p.remaining ?? 0) +
    ' · position=' + (p.current_position ?? '?') +
    ' · reopened=' + (p.reopened_page_count ?? 0) +
    ' · issues=' + (p.issue_count ?? 0);
}

async function loadNext() {
  const r = await fetch('/api/next?reviewer=' + encodeURIComponent(reviewer));
  const data = await r.json();
  const status = document.getElementById('status');
  const img = document.getElementById('overlay');
  const actions = document.getElementById('actions');
  actions.innerHTML = '';
  if (data.error) {
    status.textContent = 'Error: ' + data.error;
    img.removeAttribute('src');
    current = null;
    return;
  }
  const prog = progressText(data.progress);
  if (!data.opaque_page_reference) {
    status.textContent = (data.message || 'Coverage queue empty') +
      (prog ? ' · ' + prog : '');
    img.removeAttribute('src');
    current = null;
    return;
  }
  current = data;
  status.textContent = 'page=' + data.opaque_page_reference +
    ' · doc=' + data.opaque_document_reference +
    ' · crops=' + data.crop_count +
    (prog ? ' · ' + prog : '');
  img.src = '/api/overlay/' + encodeURIComponent(data.opaque_page_reference);
  for (const outcome of outcomes) {
    const b = document.createElement('button');
    b.textContent = outcome;
    b.onclick = () => submit(outcome);
    actions.appendChild(b);
  }
  const reopen = document.createElement('button');
  reopen.textContent = 'reopen_last_completed (if any)';
  reopen.onclick = () => submitReopen();
  actions.appendChild(reopen);
}

async function submit(outcome) {
  if (!current) return;
  const body = {
    opaque_page_reference: current.opaque_page_reference,
    opaque_document_reference: current.opaque_document_reference,
    reviewer_id: reviewer,
    action: 'resolve',
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

async function submitReopen() {
  const body = {
    reviewer_id: reviewer,
    action: 'reopen',
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

if (!reviewer) {
  document.getElementById('status').textContent =
    'Missing reviewer. Start with --reviewer and open the printed URL.';
} else {
  loadNext();
}
</script>
</body>
</html>
"""


def _ensure_repo_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def make_handler(private_root: Path, *, expected_reviewer: str) -> type[BaseHTTPRequestHandler]:
    _ensure_repo_path()
    from backend.app.datasets.phase5.coverage import (
        coverage_dir,
        coverage_progress,
        current_coverage_state,
        page_artefact_hashes,
    )
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

        def _check_reviewer(self, reviewer_id: str) -> str | None:
            if not reviewer_id or len(reviewer_id) > 64:
                return "reviewer_id required (opaque, max 64 chars)"
            if reviewer_id != expected_reviewer:
                return "reviewer_id does not match server --reviewer"
            return None

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._html(200, HTML_PAGE)
                return
            if parsed.path == "/api/next":
                qs = parse_qs(parsed.query)
                reviewer_id = (qs.get("reviewer") or [""])[0]
                err = self._check_reviewer(reviewer_id)
                if err:
                    self._json(400, {"error": err})
                    return
                queues = read_jsonl(queue_path, CoverageQueueManifest)
                progress = coverage_progress(private_root)
                if not queues:
                    self._json(
                        200,
                        {
                            "opaque_page_reference": None,
                            "message": "No coverage queue",
                            "progress": progress,
                        },
                    )
                    return
                queue = queues[-1]
                state = current_coverage_state(private_root)
                done = set(state["current"].keys())
                remaining = [e for e in queue.entries if e.opaque_page_reference not in done]
                if not remaining:
                    self._json(
                        200,
                        {
                            "opaque_page_reference": None,
                            "message": "Coverage queue empty",
                            "progress": progress,
                        },
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
                        "progress": progress,
                    },
                )
                return
            if parsed.path.startswith("/api/overlay/"):
                page_ref = parsed.path[len("/api/overlay/") :]
                if "/" in page_ref or ".." in page_ref or "\\" in page_ref:
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
            reviewer_id = str(body.get("reviewer_id") or "")
            err = self._check_reviewer(reviewer_id)
            if err:
                self._json(400, {"error": err})
                return
            action = str(body.get("action") or "resolve")
            state = current_coverage_state(private_root)
            current_map = state["current"]

            try:
                if action == "reopen":
                    # Reopen the most recently completed page for this reviewer.
                    if not current_map:
                        self._json(400, {"error": "no completed page to reopen"})
                        return
                    # Prefer explicit page if provided; else last completed in queue order.
                    page_ref = body.get("opaque_page_reference")
                    if page_ref:
                        prior = current_map.get(str(page_ref))
                    else:
                        queues = read_jsonl(queue_path, CoverageQueueManifest)
                        prior = None
                        if queues:
                            for entry in reversed(queues[-1].entries):
                                if entry.opaque_page_reference in current_map:
                                    prior = current_map[entry.opaque_page_reference]
                                    break
                    if prior is None:
                        self._json(400, {"error": "no completed page to reopen"})
                        return
                    page_hash, overlay_hash = page_artefact_hashes(
                        private_root, prior.opaque_page_reference
                    )
                    if page_hash is None or overlay_hash is None:
                        self._json(400, {"error": "missing page or overlay artefacts"})
                        return
                    event = CoverageEvent(
                        coverage_event_id=new_coverage_event_id(),
                        opaque_page_reference=prior.opaque_page_reference,
                        opaque_document_reference=prior.opaque_document_reference,
                        reviewer_id=reviewer_id,
                        action="reopen",
                        outcome=None,
                        page_render_hash=page_hash,
                        overlay_hash=overlay_hash,
                        supersedes_event_id=prior.coverage_event_id,
                        created_at=datetime.now(UTC),
                    )
                else:
                    page_ref = str(body["opaque_page_reference"])
                    doc_ref = str(body["opaque_document_reference"])
                    outcome = str(body["outcome"])
                    page_hash, overlay_hash = page_artefact_hashes(private_root, page_ref)
                    if page_hash is None or overlay_hash is None:
                        self._json(400, {"error": "missing page or overlay artefacts"})
                        return
                    prior = current_map.get(page_ref)
                    # Reject accidental duplicate resolve without reopen.
                    if prior is not None and not body.get("supersede"):
                        self._json(
                            409,
                            {
                                "error": (
                                    "page already has a current resolution; "
                                    "reopen first to supersede"
                                )
                            },
                        )
                        return
                    event = CoverageEvent(
                        coverage_event_id=new_coverage_event_id(),
                        opaque_page_reference=page_ref,
                        opaque_document_reference=doc_ref,
                        reviewer_id=reviewer_id,
                        action="resolve",
                        outcome=outcome,
                        page_render_hash=page_hash,
                        overlay_hash=overlay_hash,
                        supersedes_event_id=(
                            prior.coverage_event_id if prior is not None else None
                        ),
                        issue_flags=list(body.get("issue_flags") or []),
                        note=body.get("note"),
                        created_at=datetime.now(UTC),
                    )
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            append_jsonl(events_path, [event])
            self._json(
                200,
                {
                    "ok": True,
                    "coverage_event_id": event.coverage_event_id,
                    "action": event.action,
                },
            )

    return Handler


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_path()
    from backend.app.datasets.phase5.paths import default_private_root

    parser = argparse.ArgumentParser(description="Phase 5 loopback coverage reviewer")
    parser.add_argument("--root", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Opaque coverage reviewer id (e.g. cov_reviewer_01)",
    )
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing non-loopback bind", file=sys.stderr)
        return 2
    reviewer = str(args.reviewer).strip()
    if not reviewer or len(reviewer) > 64:
        print("reviewer must be a non-empty opaque id (max 64 chars)", file=sys.stderr)
        return 2
    private_root = Path(args.root) if args.root else default_private_root()
    if not private_root.is_dir():
        print(f"Private root missing: {private_root}", file=sys.stderr)
        return 1
    handler = make_handler(private_root, expected_reviewer=reviewer)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Phase 5 coverage review on http://{args.host}:{args.port}/?reviewer={reviewer}")
    print("Backup private manifests before long interruptions: pnpm phase5:dataset:backup")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
