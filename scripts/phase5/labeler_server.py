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
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Phase 5 crop labeler (loopback)</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1rem; }
  .meta { color: #444; font-size: 0.9rem; }
  kbd { background: #eee; padding: 0.1rem 0.35rem; border-radius: 3px; }
  .warn { color: #a40; }
  #toolbar {
    display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap;
    margin: 0.5rem 0 1rem;
  }
  #grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 0.75rem;
  }
  .card {
    background: #1e1e1e;
    border: 2px solid #444;
    border-radius: 6px;
    padding: 0.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .card.selected { border-color: #4ea1ff; }
  .card.busy { opacity: 0.45; pointer-events: none; }
  .card.done { opacity: 0.25; }
  .crop-wrap {
    background: #111;
    min-height: 100px;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }
  .crop-wrap img {
    background: #fff;
    image-rendering: pixelated;
    image-rendering: crisp-edges;
    max-width: 100%;
  }
  .btns { display: flex; flex-wrap: wrap; gap: 0.25rem; }
  .btns button {
    font-size: 0.75rem;
    padding: 0.2rem 0.4rem;
    cursor: pointer;
  }
  .btns button.p { background: #dcefdc; }
  .btns button.h { background: #f5e6c8; }
  .btns button.u { background: #e8e0f5; }
  .btns button.n { background: #ddd; }
  .btns button.x { background: #f5d0d0; }
  .flags { display: flex; flex-wrap: wrap; gap: 0.2rem; }
  .flags button {
    font-size: 0.65rem;
    padding: 0.15rem 0.3rem;
    cursor: pointer;
    background: #333;
    color: #ddd;
    border: 1px solid #555;
  }
  .flags button.on { background: #5a6a3a; border-color: #9c3; color: #fff; }
  .id { color: #aaa; font-size: 0.7rem; word-break: break-all; }
</style>
</head>
<body>
<h1>Phase 5 blind labeler (grid)</h1>
<p class="meta">Loopback only. No OCR text, filenames, provenance, or predictions.
Toggle quality flags on a card (optional), then click a label.
Or select a card and use keys:
<kbd>P</kbd> printed · <kbd>H</kbd> handwritten · <kbd>U</kbd> uncertain ·
<kbd>N</kbd> non-text · <kbd>S</kbd> signature→handwritten · <kbd>X</kbd> exclude ·
<kbd>Z</kbd> skip. Flags do not change the label; use <kbd>X</kbd> for unusable crops.</p>
<div id="toolbar">
  <span id="status" class="meta">Loading…</span>
  <button type="button" id="reload">Load next page</button>
  <label class="meta">Page size
    <select id="pagesize">
      <option value="12">12</option>
      <option value="24" selected>24</option>
      <option value="48">48</option>
    </select>
  </label>
</div>
<p id="conflict" class="warn"></p>
<div id="grid"></div>
<script>
const params = new URLSearchParams(location.search);
const role = params.get('role') || 'primary';
const reviewer = params.get('reviewer') || '';
const queue = params.get('queue') || '';
const qualityFlagNames = [
  'crop_too_tight','crop_too_broad','blurred','low_resolution','mixed_content',
  'partial_characters','rotation_problem','possible_duplicate','requires_page_context'
];
let items = [];
let selectedId = null;
let remaining = 0;
const flagsByCrop = {};

function scaleCropImage(img) {
  const nw = img.naturalWidth || 1;
  const nh = img.naturalHeight || 1;
  const target = 180;
  const scale = Math.min(10, Math.max(1, Math.ceil(target / Math.max(nw, nh))));
  img.style.width = (nw * scale) + 'px';
  img.style.height = (nh * scale) + 'px';
}

function qs() {
  return 'role=' + encodeURIComponent(role) +
    '&reviewer=' + encodeURIComponent(reviewer) +
    '&queue=' + encodeURIComponent(queue);
}

function flagsFor(cropId) {
  if (!flagsByCrop[cropId]) flagsByCrop[cropId] = [];
  return flagsByCrop[cropId];
}

async function submitOne(item, action, label) {
  const card = document.querySelector('[data-crop-id=\"' + item.crop_id + '\"]');
  if (card) card.classList.add('busy');
  const body = {
    crop_id: item.crop_id,
    crop_sha256: item.sha256,
    reviewer_id: reviewer,
    role: role,
    queue_name: queue,
    action: action,
    label: label || null,
    quality_flags: flagsFor(item.crop_id).slice(),
  };
  const r = await fetch('/api/review', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    document.getElementById('status').textContent = 'Error: ' + await r.text();
    if (card) card.classList.remove('busy');
    return false;
  }
  delete flagsByCrop[item.crop_id];
  items = items.filter(x => x.crop_id !== item.crop_id);
  if (selectedId === item.crop_id) selectedId = null;
  remaining = Math.max(0, remaining - 1);
  if (card) {
    card.classList.add('done');
    card.remove();
  }
  updateStatus();
  if (items.length === 0 && remaining > 0) await loadBatch();
  return true;
}

function updateStatus() {
  document.getElementById('status').textContent =
    'queue=' + queue + ' · role=' + role +
    ' · on screen=' + items.length +
    ' · remaining≈' + remaining +
    (selectedId ? ' · selected=' + selectedId : '');
}

function renderGrid() {
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  for (const item of items) {
    const card = document.createElement('div');
    card.className = 'card' + (selectedId === item.crop_id ? ' selected' : '');
    card.dataset.cropId = item.crop_id;
    card.onclick = (ev) => {
      if (ev.target.tagName === 'BUTTON') return;
      selectedId = item.crop_id;
      renderGrid();
    };
    const wrap = document.createElement('div');
    wrap.className = 'crop-wrap';
    const img = document.createElement('img');
    img.alt = 'crop';
    img.onload = () => scaleCropImage(img);
    img.src = '/api/crop/' + encodeURIComponent(item.crop_id) + '?v=' + item.sha256.slice(0, 12);
    wrap.appendChild(img);
    const id = document.createElement('div');
    id.className = 'id';
    id.textContent = item.crop_id;
    const flags = document.createElement('div');
    flags.className = 'flags';
    const selected = flagsFor(item.crop_id);
    for (const name of qualityFlagNames) {
      const fb = document.createElement('button');
      fb.type = 'button';
      fb.textContent = name + (selected.includes(name) ? ' ✓' : '');
      if (selected.includes(name)) fb.classList.add('on');
      fb.onclick = (ev) => {
        ev.stopPropagation();
        const cur = flagsFor(item.crop_id);
        if (cur.includes(name)) flagsByCrop[item.crop_id] = cur.filter(x => x !== name);
        else cur.push(name);
        renderGrid();
      };
      flags.appendChild(fb);
    }
    const btns = document.createElement('div');
    btns.className = 'btns';
    const actions = [
      ['P', 'p', 'label', 'printed'],
      ['H', 'h', 'label', 'handwritten'],
      ['U', 'u', 'label', 'uncertain'],
      ['N', 'n', 'label', 'non_text'],
      ['S', 'h', 'label', 'handwritten'],
      ['X', 'x', 'exclude', null],
    ];
    for (const [text, cls, action, label] of actions) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = cls;
      b.textContent = text;
      b.onclick = (ev) => {
        ev.stopPropagation();
        submitOne(item, action, label);
      };
      btns.appendChild(b);
    }
    card.appendChild(wrap);
    card.appendChild(id);
    card.appendChild(flags);
    card.appendChild(btns);
    grid.appendChild(card);
  }
  updateStatus();
}

async function loadBatch() {
  if (!reviewer || !queue) {
    document.getElementById('status').textContent =
      'Missing reviewer or queue. Start with --queue and --reviewer.';
    return;
  }
  const limit = document.getElementById('pagesize').value || '24';
  document.getElementById('status').textContent = 'Loading…';
  const r = await fetch('/api/batch?' + qs() + '&limit=' + encodeURIComponent(limit));
  const data = await r.json();
  if (data.error) {
    document.getElementById('status').textContent = 'Error: ' + data.error;
    items = [];
    renderGrid();
    return;
  }
  items = data.items || [];
  remaining = data.remaining || 0;
  selectedId = items.length ? items[0].crop_id : null;
  if (!items.length) {
    document.getElementById('status').textContent = data.message || 'Queue complete';
  }
  renderGrid();
}

document.getElementById('reload').onclick = () => loadBatch();
document.getElementById('pagesize').onchange = () => loadBatch();
document.addEventListener('keydown', (ev) => {
  if (!selectedId) return;
  const item = items.find(x => x.crop_id === selectedId);
  if (!item) return;
  const k = ev.key.toLowerCase();
  if (k === 'p') submitOne(item, 'label', 'printed');
  else if (k === 'h') submitOne(item, 'label', 'handwritten');
  else if (k === 'u') submitOne(item, 'label', 'uncertain');
  else if (k === 'n') submitOne(item, 'label', 'non_text');
  else if (k === 's') submitOne(item, 'label', 'handwritten');
  else if (k === 'x') submitOne(item, 'exclude', null);
  else if (k === 'z') submitOne(item, 'skip', null);
});

loadBatch();
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
    crop_cache: dict[str, Any] = {"mtime": None, "by_id": {}}
    events_cache: dict[str, Any] = {"mtime": None, "size": None, "rows": []}

    def _load_queue(queue_name: str) -> ReviewQueueManifest:
        if queue_name not in QUEUE_FILES:
            raise ValueError(f"unknown queue: {queue_name}")
        path = manifest_path(private_root, QUEUE_FILES[queue_name])
        rows = read_jsonl(path, ReviewQueueManifest)
        if not rows:
            raise ValueError(f"queue file empty or missing: {queue_name}")
        return rows[-1]

    def _crops_by_id() -> dict[str, CropRecord]:
        mtime = crops_path.stat().st_mtime if crops_path.is_file() else None
        if crop_cache["mtime"] != mtime:
            by_id: dict[str, CropRecord] = {
                c.crop_id: c for c in read_jsonl(crops_path, CropRecord)
            }
            crop_cache["by_id"] = by_id
            crop_cache["mtime"] = mtime
        return cast(dict[str, CropRecord], crop_cache["by_id"])

    def _events() -> list[ReviewEvent]:
        mtime = events_path.stat().st_mtime if events_path.is_file() else None
        size = events_path.stat().st_size if events_path.is_file() else 0
        if events_cache["mtime"] != mtime or events_cache["size"] != size:
            rows: list[ReviewEvent] = (
                read_jsonl(events_path, ReviewEvent) if events_path.is_file() else []
            )
            events_cache["rows"] = rows
            events_cache["mtime"] = mtime
            events_cache["size"] = size
        return cast(list[ReviewEvent], events_cache["rows"])

    def _invalidate_events() -> None:
        events_cache["mtime"] = None
        events_cache["size"] = None
        events_cache["rows"] = []

    def _pending_candidates(
        *,
        queue: ReviewQueueManifest,
        role: str,
        reviewer_id: str,
        queue_name: str,
    ) -> list[Any] | tuple[str, int]:
        crops = _crops_by_id()
        events = _events()
        by_crop: dict[str, list[Any]] = {}
        for ev in events:
            by_crop.setdefault(ev.crop_id, []).append(ev)

        candidates: list[Any] = []
        for entry in queue.entries:
            crop = crops.get(entry.crop_id)
            if crop is None:
                continue
            if entry.crop_sha256 != crop.sha256:
                return ("crop hash mismatch — rebuild queues", 409)
            evs = [e for e in by_crop.get(crop.crop_id, []) if e.crop_sha256 == crop.sha256]
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
                    e.role: e.label for e in evs if e.action == "label" and e.label is not None
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
        return candidates

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
            events = _events()
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
                result = _pending_candidates(
                    queue=queue, role=role, reviewer_id=reviewer_id, queue_name=queue_name
                )
                if isinstance(result, tuple):
                    self._json(result[1], {"error": result[0]})
                    return
                candidates = result
                if not candidates:
                    self._json(200, {"crop_id": None, "message": "Queue empty for role"})
                    return
                crop = candidates[0]
                conflict_hint = ""
                if role == "adjudicator":
                    by_crop_events = [
                        e
                        for e in _events()
                        if e.crop_id == crop.crop_id and e.crop_sha256 == crop.sha256
                    ]
                    labels = {
                        e.role: e.label
                        for e in by_crop_events
                        if e.action == "label" and e.label is not None
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

            if parsed.path == "/api/batch":
                qs = parse_qs(parsed.query)
                role = (qs.get("role") or ["primary"])[0]
                reviewer_id = (qs.get("reviewer") or [""])[0]
                queue_name = (qs.get("queue") or [default_queue])[0]
                try:
                    limit = max(1, min(96, int((qs.get("limit") or ["24"])[0])))
                except ValueError:
                    limit = 24
                queue, err = self._validate_access(
                    queue_name=queue_name, role=role, reviewer_id=reviewer_id
                )
                if err or queue is None:
                    self._json(400, {"error": err or "invalid queue"})
                    return
                result = _pending_candidates(
                    queue=queue, role=role, reviewer_id=reviewer_id, queue_name=queue_name
                )
                if isinstance(result, tuple):
                    self._json(result[1], {"error": result[0]})
                    return
                candidates = result
                page = candidates[:limit]
                self._json(
                    200,
                    {
                        "remaining": len(candidates),
                        "items": [{"crop_id": c.crop_id, "sha256": c.sha256} for c in page],
                        "message": None if page else "Queue empty for role",
                    },
                )
                return

            if parsed.path.startswith("/api/crop/"):
                crop_id = parsed.path[len("/api/crop/") :]
                if "/" in crop_id or ".." in crop_id:
                    self.send_error(400, "bad crop id")
                    return
                found = _crops_by_id().get(crop_id)
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
            crop = _crops_by_id().get(event.crop_id)
            if crop is None:
                self._json(404, {"error": "unknown crop"})
                return
            if event.crop_sha256 != crop.sha256:
                self._json(409, {"error": "crop hash mismatch — reload queue"})
                return
            append_jsonl(events_path, [event])
            _invalidate_events()
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
