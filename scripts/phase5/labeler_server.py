#!/usr/bin/env python3
"""Loopback-only Phase 5 blind crop labeler (127.0.0.1).

Requires an explicit queue name. Default human workflow is pilot-primary.
Full-primary requires --authorise-full-queue. Not mounted in FastAPI.
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

ROOT = Path(__file__).resolve().parents[2]

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
  .flags button { margin: 0.15rem; }
</style>
</head>
<body>
<h1>Phase 5 blind labeler</h1>
<p class="meta">Loopback only. No OCR text, filenames, provenance, or sampling reasons.
Keys: <kbd>P</kbd> printed · <kbd>H</kbd> handwritten · <kbd>U</kbd> uncertain ·
<kbd>N</kbd> non-text · <kbd>S</kbd> signature→handwritten · <kbd>X</kbd> exclude ·
<kbd>Z</kbd> skip. Quality flags do not change the label.</p>
<p id="status" class="meta">Loading…</p>
<p id="conflict" class="warn"></p>
<img id="crop" alt="crop"/>
<div class="flags" id="flags"></div>
<script>
const params = new URLSearchParams(location.search);
const role = params.get('role') || 'primary';
const reviewer = params.get('reviewer') || '';
const queue = params.get('queue') || '';
const qualityFlags = [
  'crop_too_tight','crop_too_broad','blurred','low_resolution','mixed_content',
  'partial_characters','rotation_problem','possible_duplicate','requires_page_context'
];
let current = null;
let pendingFlags = [];

function renderFlags() {
  const el = document.getElementById('flags');
  el.innerHTML = '';
  for (const f of qualityFlags) {
    const b = document.createElement('button');
    b.textContent = f + (pendingFlags.includes(f) ? ' ✓' : '');
    b.onclick = () => {
      if (pendingFlags.includes(f)) pendingFlags = pendingFlags.filter(x => x !== f);
      else pendingFlags.push(f);
      renderFlags();
    };
    el.appendChild(b);
  }
}

async function loadNext() {
  if (!reviewer || !queue) {
    document.getElementById('status').textContent =
      'Missing reviewer or queue. Start with --queue and --reviewer.';
    return;
  }
  const r = await fetch('/api/next?role=' + encodeURIComponent(role) +
    '&reviewer=' + encodeURIComponent(reviewer) +
    '&queue=' + encodeURIComponent(queue));
  const data = await r.json();
  const status = document.getElementById('status');
  const conflict = document.getElementById('conflict');
  const img = document.getElementById('crop');
  if (data.error) {
    status.textContent = 'Error: ' + data.error;
    img.removeAttribute('src');
    current = null;
    return;
  }
  if (!data.crop_id) {
    status.textContent = data.message || 'Queue empty';
    img.removeAttribute('src');
    current = null;
    return;
  }
  current = data;
  pendingFlags = [];
  renderFlags();
  status.textContent = 'crop_id=' + data.crop_id + ' · role=' + role +
    ' · queue=' + queue + ' · remaining≈' + (data.remaining ?? '?');
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
    queue_name: queue,
    action: action,
    label: label || null,
    quality_flags: pendingFlags.slice(),
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

renderFlags();
loadNext();
</script>
</body>
</html>
"""

QUEUE_FILES = {
    "pilot-primary": "pilot-primary-queue.jsonl",
    "pilot-secondary": "pilot-secondary-queue.jsonl",
    "full-primary": "primary-review-queue.jsonl",
    "adjudication": "adjudication-queue.jsonl",
    "prototype-primary": "prototype-primary-queue.jsonl",
}

ROLE_FOR_QUEUE = {
    "pilot-primary": "primary",
    "pilot-secondary": "secondary",
    "full-primary": "primary",
    "adjudication": "adjudicator",
    "prototype-primary": "primary",
}


def _reviewer_id_ok(queue_name: str, reviewer_id: str) -> bool:
    if not reviewer_id:
        return False
    if reviewer_id.startswith("rev_"):
        return True
    # Prototype path accepts opaque proto_reviewer_* (ADR 0053 / Task A).
    return queue_name == "prototype-primary" and reviewer_id.startswith("proto_reviewer_")


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


def make_handler(
    private_root: Path,
    *,
    default_queue: str,
    authorise_full_queue: bool,
    expected_reviewer: str | None,
) -> type[BaseHTTPRequestHandler]:
    _ensure_repo_path()
    from backend.app.datasets.phase5.hashes import sha256_file
    from backend.app.datasets.phase5.ids import new_review_id
    from backend.app.datasets.phase5.jsonl_io import append_jsonl, read_jsonl
    from backend.app.datasets.phase5.paths import manifest_path
    from backend.app.datasets.phase5.schemas import CropRecord, ReviewEvent, ReviewQueueManifest

    crops_path = manifest_path(private_root, "crop-manifest.jsonl")
    events_path = manifest_path(private_root, "review-events.jsonl")
    context_path = manifest_path(private_root, "context-review-worklist.jsonl")

    def _load_queue(queue_name: str) -> ReviewQueueManifest:
        if queue_name not in QUEUE_FILES:
            raise ValueError(f"unknown queue: {queue_name}")
        path = manifest_path(private_root, QUEUE_FILES[queue_name])
        rows = read_jsonl(path, ReviewQueueManifest)
        if not rows:
            raise ValueError(f"queue file empty or missing: {queue_name}")
        return rows[-1]

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

        def _validate_access(
            self, *, queue_name: str, role: str, reviewer_id: str
        ) -> tuple[ReviewQueueManifest | None, str | None]:
            if not _reviewer_id_ok(queue_name, reviewer_id):
                if queue_name == "prototype-primary":
                    return None, "reviewer_id must be opaque rev_<id> or proto_reviewer_<id>"
                return None, "reviewer_id must be opaque rev_<id>"
            if expected_reviewer and reviewer_id != expected_reviewer:
                return None, "reviewer_id does not match server --reviewer"
            if queue_name not in QUEUE_FILES:
                return None, f"unknown queue: {queue_name}"
            expected_role = ROLE_FOR_QUEUE[queue_name]
            if role != expected_role:
                return None, f"role {role} incompatible with queue {queue_name}"
            try:
                queue = _load_queue(queue_name)
            except ValueError as exc:
                return None, str(exc)
            if queue_name == "full-primary" and not authorise_full_queue:
                return None, "full-primary requires --authorise-full-queue"
            if (
                queue_name == "full-primary"
                and not queue.authorised_for_review
                and not authorise_full_queue
            ):
                return None, "full primary queue not authorised for review until pilot approval"
            if queue_name == "adjudication" and not queue.entries:
                return None, "adjudication queue empty — no conflicts yet"
            # Stale crop-manifest hash
            if queue.crop_manifest_sha256:
                current = sha256_file(crops_path) if crops_path.is_file() else None
                if current != queue.crop_manifest_sha256:
                    return None, "stale queue hash — rebuild queues"
            # Same reviewer cannot hold both pilot primary and secondary roles.
            events = read_jsonl(events_path, ReviewEvent)
            other_role = (
                "secondary" if role == "primary" else "primary" if role == "secondary" else None
            )
            if other_role and queue_name.startswith("pilot-"):
                for ev in events:
                    if (
                        ev.reviewer_id == reviewer_id
                        and ev.role == other_role
                        and (ev.queue_name or "").startswith("pilot-")
                    ):
                        return (
                            None,
                            "same reviewer_id cannot serve both pilot primary and secondary",
                        )
            return queue, None

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._html(200, HTML_PAGE)
                return
            if parsed.path == "/api/next":
                qs = parse_qs(parsed.query)
                role = (qs.get("role") or ["primary"])[0]
                reviewer_id = (qs.get("reviewer") or [""])[0]
                queue_name = (qs.get("queue") or [default_queue])[0]
                queue, err = self._validate_access(
                    queue_name=queue_name, role=role, reviewer_id=reviewer_id
                )
                if err or queue is None:
                    self._json(400, {"error": err or "invalid queue"})
                    return
                crops = {c.crop_id: c for c in read_jsonl(crops_path, CropRecord)}
                events = read_jsonl(events_path, ReviewEvent)
                by_crop: dict[str, list[Any]] = {}
                for ev in events:
                    by_crop.setdefault(ev.crop_id, []).append(ev)

                candidates: list[Any] = []
                for entry in queue.entries:
                    crop = crops.get(entry.crop_id)
                    if crop is None:
                        continue
                    if entry.crop_sha256 != crop.sha256:
                        self._json(409, {"error": "crop hash mismatch — rebuild queues"})
                        return
                    evs = [e for e in by_crop.get(crop.crop_id, []) if e.crop_sha256 == crop.sha256]
                    # Progress isolation: only this reviewer's completion for this role/queue.
                    done_for_reviewer = any(
                        e.role == role
                        and e.reviewer_id == reviewer_id
                        and e.action in {"label", "exclude"}
                        and (e.queue_name is None or e.queue_name == queue_name)
                        for e in evs
                    )
                    if done_for_reviewer:
                        continue
                    if role == "adjudicator":
                        labels = {
                            e.role: e.label
                            for e in evs
                            if e.action == "label" and e.label is not None
                        }
                        if not (
                            "primary" in labels
                            and "secondary" in labels
                            and labels["primary"] != labels["secondary"]
                        ):
                            continue
                        if any(e.role == "adjudicator" and e.action == "label" for e in evs):
                            continue
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
                try:
                    path = _safe_crop_path(private_root, found)
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
            queue_name = str(body.get("queue_name") or default_queue)
            role = str(body.get("role") or "")
            reviewer_id = str(body.get("reviewer_id") or "")
            queue, err = self._validate_access(
                queue_name=queue_name, role=role, reviewer_id=reviewer_id
            )
            if err or queue is None:
                self._json(400, {"error": err or "invalid queue"})
                return
            try:
                event = ReviewEvent(
                    review_id=new_review_id(),
                    crop_id=str(body["crop_id"]),
                    crop_sha256=str(body["crop_sha256"]),
                    reviewer_id=reviewer_id,
                    role=role,  # validated above
                    action=body["action"],
                    label=body.get("label"),
                    note=body.get("note"),
                    quality_flags=list(body.get("quality_flags") or []),
                    queue_name=queue_name,
                    created_at=datetime.now(UTC),
                )
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            # Crop must be in the selected queue.
            if event.crop_id not in {e.crop_id for e in queue.entries}:
                self._json(403, {"error": "crop not in selected queue"})
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
            if "requires_page_context" in event.quality_flags:
                append_jsonl(
                    context_path,
                    [
                        ReviewEvent(
                            review_id=new_review_id(),
                            crop_id=event.crop_id,
                            crop_sha256=event.crop_sha256,
                            reviewer_id=event.reviewer_id,
                            role=event.role,
                            action="flag_quality",
                            label=None,
                            note="requires_page_context",
                            quality_flags=["requires_page_context"],
                            queue_name=queue_name,
                            created_at=datetime.now(UTC),
                        )
                    ],
                )
            self._json(200, {"ok": True, "review_id": event.review_id})

    return Handler


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_path()
    from backend.app.datasets.phase5.paths import default_private_root

    parser = argparse.ArgumentParser(description="Phase 5 loopback crop labeler")
    parser.add_argument("--root", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--queue",
        required=True,
        choices=sorted(QUEUE_FILES.keys()),
        help=(
            "Required queue name "
            "(prototype-primary|pilot-primary|pilot-secondary|full-primary|adjudication)"
        ),
    )
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Opaque reviewer id (rev_<id> or proto_reviewer_<id> for prototype-primary)",
    )
    parser.add_argument(
        "--authorise-full-queue",
        action="store_true",
        help="Required to serve full-primary queue",
    )
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing non-loopback bind", file=sys.stderr)
        return 2
    if not _reviewer_id_ok(str(args.queue), str(args.reviewer)):
        print(
            "reviewer must start with rev_ (or proto_reviewer_ for prototype-primary)",
            file=sys.stderr,
        )
        return 2
    if args.queue == "full-primary" and not args.authorise_full_queue:
        print("full-primary requires --authorise-full-queue", file=sys.stderr)
        return 2
    private_root = Path(args.root) if args.root else default_private_root()
    if not private_root.is_dir():
        print(f"Private root missing: {private_root}", file=sys.stderr)
        return 1
    role = ROLE_FOR_QUEUE[args.queue]
    handler = make_handler(
        private_root,
        default_queue=args.queue,
        authorise_full_queue=bool(args.authorise_full_queue),
        expected_reviewer=str(args.reviewer),
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        f"Phase 5 labeler on http://{args.host}:{args.port}/"
        f"?role={role}&queue={args.queue}&reviewer={args.reviewer}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
