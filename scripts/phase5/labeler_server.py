#!/usr/bin/env python3
"""Loopback-only Phase 5 blind crop labeler (127.0.0.1).

Not mounted in production FastAPI. Not part of the frontend bundle.
Stores no private data in localStorage. Append-only review events.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Phase 5 crop labeler (loopback)</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1.5rem; max-width: 960px; }
  #crop { max-width: 100%; border: 1px solid #ccc; background: #f7f7f7; }
  .meta { color: #444; font-size: 0.9rem; }
  kbd { background: #eee; padding: 0.1rem 0.35rem; border-radius: 3px; }
  .warn { color: #a40; }
</style>
</head>
<body>
<h1>Phase 5 blind labeler</h1>
<p class="meta">Loopback only. No OCR text, filenames, or case names are shown.
Keys: <kbd>P</kbd> printed · <kbd>H</kbd> handwritten · <kbd>U</kbd> uncertain ·
<kbd>N</kbd> non-text · <kbd>S</kbd> signature→handwritten · <kbd>X</kbd> exclude ·
<kbd>Z</kbd> skip · adjudicators see conflicts only.</p>
<p id="status" class="meta">Loading…</p>
<p id="conflict" class="warn"></p>
<img id="crop" alt="crop"/>
<script>
const role = new URLSearchParams(location.search).get('role') || 'primary';
const reviewer = new URLSearchParams(location.search).get('reviewer') || ('rev_' + role);
let current = null;

async function loadNext() {
  const r = await fetch('/api/next?role=' + encodeURIComponent(role));
  const data = await r.json();
  const status = document.getElementById('status');
  const conflict = document.getElementById('conflict');
  const img = document.getElementById('crop');
  if (!data.crop_id) {
    status.textContent = data.message || 'Queue empty';
    img.removeAttribute('src');
    current = null;
    return;
  }
  current = data;
  status.textContent = 'crop_id=' + data.crop_id + ' · role=' + role +
    ' · remaining≈' + (data.remaining ?? '?');
  conflict.textContent = data.conflict_hint || '';
  img.src = '/api/crop/' + encodeURIComponent(data.crop_id) + '?v=' + data.sha256.slice(0, 12);
}

async function submit(action, label) {
  if (!current) return;
  const body = {
    crop_id: current.crop_id,
    crop_sha256: current.sha256,
    reviewer_id: reviewer,
    role: role,
    action: action,
    label: label || null,
  };
  const r = await fetch('/api/review', {
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

document.addEventListener('keydown', (ev) => {
  const k = ev.key.toLowerCase();
  if (k === 'p') submit('label', 'printed');
  else if (k === 'h') submit('label', 'handwritten');
  else if (k === 'u') submit('label', 'uncertain');
  else if (k === 'n') submit('label', 'non_text');
  else if (k === 's') submit('label', 'handwritten');
  else if (k === 'x') submit('exclude', null);
  else if (k === 'z') submit('skip', null);
});

loadNext();
</script>
</body>
</html>
"""


def _ensure_repo_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


def _safe_crop_path(private_root: Path, crop: Any) -> Path:
    rel = Path(crop.crop_relpath)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("path traversal rejected")
    path = (private_root / rel).resolve()
    root = private_root.resolve()
    if not str(path).startswith(str(root)):
        raise ValueError("path traversal rejected")
    if not path.is_file():
        raise FileNotFoundError(crop.crop_id)
    return path


def make_handler(private_root: Path) -> type[BaseHTTPRequestHandler]:
    _ensure_repo_path()
    from backend.app.datasets.phase5.ids import new_review_id
    from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl
    from backend.app.datasets.phase5.paths import manifest_path
    from backend.app.datasets.phase5.schemas import CropRecord, ReviewEvent

    crops_path = manifest_path(private_root, "crop-manifest.jsonl")
    events_path = manifest_path(private_root, "review-events.jsonl")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("labeler: " + (fmt % args) + "\n")

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
                qs = parse_qs(parsed.query)
                role = (qs.get("role") or ["primary"])[0]
                if role not in {"primary", "secondary", "adjudicator"}:
                    self._json(400, {"error": "bad role"})
                    return
                crops = read_jsonl(crops_path, CropRecord)
                events = read_jsonl(events_path, ReviewEvent)
                by_crop: dict[str, list[Any]] = {}
                for ev in events:
                    by_crop.setdefault(ev.crop_id, []).append(ev)

                candidates: list[Any] = []
                for crop in crops:
                    evs = [e for e in by_crop.get(crop.crop_id, []) if e.crop_sha256 == crop.sha256]
                    roles = {e.role for e in evs if e.action == "label"}
                    labels = {
                        e.role: e.label for e in evs if e.action == "label" and e.label is not None
                    }
                    if any(e.action == "exclude" for e in evs):
                        continue
                    primary_needed = role == "primary" and "primary" not in roles
                    secondary_needed = (
                        role == "secondary" and "primary" in roles and "secondary" not in roles
                    )
                    adjudicator_needed = (
                        role == "adjudicator"
                        and "primary" in labels
                        and "secondary" in labels
                        and labels["primary"] != labels["secondary"]
                        and "adjudicator" not in roles
                    )
                    if primary_needed or secondary_needed or adjudicator_needed:
                        candidates.append(crop)

                if not candidates:
                    self._json(200, {"crop_id": None, "message": "Queue empty for role"})
                    return
                crop = candidates[0]
                conflict_hint = ""
                if role == "adjudicator":
                    labels = {
                        e.role: e.label
                        for e in by_crop.get(crop.crop_id, [])
                        if e.action == "label" and e.crop_sha256 == crop.sha256
                    }
                    conflict_hint = (
                        f"Conflict: primary={labels.get('primary')} "
                        f"secondary={labels.get('secondary')}"
                    )
                self._json(
                    200,
                    {
                        "crop_id": crop.crop_id,
                        "sha256": crop.sha256,
                        "remaining": len(candidates),
                        "conflict_hint": conflict_hint,
                    },
                )
                return

            if parsed.path.startswith("/api/crop/"):
                crop_id = parsed.path[len("/api/crop/") :]
                if "/" in crop_id or ".." in crop_id:
                    self.send_error(400, "bad crop id")
                    return
                crops_by_id = {c.crop_id: c for c in read_jsonl(crops_path, CropRecord)}
                found = crops_by_id.get(crop_id)
                if found is None:
                    self.send_error(404, "unknown crop")
                    return
                crop = found
                try:
                    path = _safe_crop_path(private_root, crop)
                except (ValueError, FileNotFoundError):
                    self.send_error(404, "crop missing")
                    return
                data = path.read_bytes()
                ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
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
            if parsed.path != "/api/review":
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
                event = ReviewEvent(
                    review_id=new_review_id(),
                    crop_id=str(body["crop_id"]),
                    crop_sha256=str(body["crop_sha256"]),
                    reviewer_id=str(body["reviewer_id"]),
                    role=body["role"],
                    action=body["action"],
                    label=body.get("label"),
                    note=None,
                    created_at=datetime.now(UTC),
                )
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            crops_by_id = {c.crop_id: c for c in read_jsonl(crops_path, CropRecord)}
            crop = crops_by_id.get(event.crop_id)
            if crop is None:
                self._json(404, {"error": "unknown crop"})
                return
            if event.crop_sha256 != crop.sha256:
                self._json(409, {"error": "crop hash mismatch — reload queue"})
                return
            append_jsonl(events_path, [event])
            self._json(200, {"ok": True, "review_id": event.review_id})

    return Handler


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_path()
    from backend.app.datasets.phase5.paths import default_private_root

    parser = argparse.ArgumentParser(description="Phase 5 loopback crop labeler")
    parser.add_argument("--root", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
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
    print(f"Phase 5 labeler on http://{args.host}:{args.port}/?role=primary")
    print("Secondary: ?role=secondary  Adjudicator: ?role=adjudicator")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
