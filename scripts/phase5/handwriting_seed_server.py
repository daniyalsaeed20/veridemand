#!/usr/bin/env python3
"""Loopback-only Phase 5 handwriting seed collector (127.0.0.1).

Human draws or selects clear handwritten regions. No OCR text, filenames,
classifier predictions, or transcription. Not mounted in FastAPI/frontend.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[2]

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Phase 5 handwriting seed collection (loopback)</title>
<style>
  :root { color-scheme: light; }
  body { font-family: system-ui, sans-serif; margin: 0; background: #f4f4f1; color: #1a1a1a; }
  header { padding: 0.75rem 1rem; background: #fff; border-bottom: 1px solid #ccc; }
  .meta { color: #444; font-size: 0.9rem; }
  .layout { display: grid; grid-template-columns: 1fr 280px; gap: 0; min-height: calc(100vh - 70px); }
  #stageWrap { overflow: hidden; background: #2a2a2a; position: relative; touch-action: none; }
  #stage { transform-origin: 0 0; position: relative; display: inline-block; }
  #pageImg { display: block; max-width: none; user-select: none; }
  #overlayCanvas { position: absolute; left: 0; top: 0; cursor: crosshair; }
  aside { padding: 1rem; background: #fff; border-left: 1px solid #ccc; }
  button, select { margin: 0.2rem 0; width: 100%; padding: 0.45rem; }
  .row { display: flex; gap: 0.35rem; }
  .row button { flex: 1; }
  label { display: block; font-size: 0.85rem; margin-top: 0.6rem; }
  #warn { color: #8a4b08; font-size: 0.85rem; min-height: 1.2em; }
  #status { font-size: 0.9rem; }
  .hint { font-size: 0.8rem; color: #555; margin-top: 0.75rem; }
  #guides { max-height: 180px; overflow: auto; font-size: 0.8rem; }
  .guide { padding: 0.25rem; border: 1px solid #ddd; margin: 0.2rem 0; cursor: pointer; }
  .guide.uncertain { border-color: #c47a00; }
  .guide.selected { background: #e8f0ff; }
</style>
</head>
<body>
<header>
  <strong>Phase 5 handwriting seed collection</strong>
  <div class="meta">Loopback only. Confirm clear handwriting only. No OCR, paths, or predictions.
  Do not use localStorage / IndexedDB.</div>
  <div id="status" class="meta">Loading…</div>
</header>
<div class="layout">
  <div id="stageWrap">
    <div id="stage">
      <img id="pageImg" alt="page render"/>
      <canvas id="overlayCanvas"></canvas>
    </div>
  </div>
  <aside>
    <div class="row">
      <button type="button" id="zoomIn">Zoom +</button>
      <button type="button" id="zoomOut">Zoom −</button>
      <button type="button" id="resetView">Reset</button>
    </div>
    <label>Category tags (optional)</label>
    <select id="categories" multiple size="6">
      <option value="digits">digits</option>
      <option value="hand_printed">hand_printed</option>
      <option value="cursive">cursive</option>
      <option value="signature">signature</option>
      <option value="correction">correction</option>
      <option value="longer_note">longer_note</option>
    </select>
    <button type="button" id="confirmDraw">Confirm drawn region as handwritten</button>
    <button type="button" id="confirmSelect">Confirm selected existing crop</button>
    <button type="button" id="clearDraw">Clear drawing</button>
    <button type="button" id="pageDone">Page done — next</button>
    <button type="button" id="noHw">No usable handwriting on page</button>
    <button type="button" id="defer">Defer page</button>
    <div id="warn"></div>
    <div class="hint">Drag on the page to draw a region. Middle-drag or Space+drag to pan.
    Existing boxes are guides only. Select a guide to reuse a clean crop, or draw a tighter
    subregion after selecting an uncertain parent.</div>
    <div id="guides"></div>
  </aside>
</div>
<script>
const reviewer = new URLSearchParams(location.search).get('reviewer') || '';
let current = null;
let guides = [];
let selectedGuide = null;
let scale = 1;
let panX = 0;
let panY = 0;
let drawing = false;
let start = null;
let draft = null;
let panning = false;
let panStart = null;
let spaceDown = false;

const stage = document.getElementById('stage');
const wrap = document.getElementById('stageWrap');
const img = document.getElementById('pageImg');
const canvas = document.getElementById('overlayCanvas');
const ctx = canvas.getContext('2d');
const statusEl = document.getElementById('status');
const warnEl = document.getElementById('warn');
const guidesEl = document.getElementById('guides');

function selectedCategories() {
  return Array.from(document.getElementById('categories').selectedOptions).map(o => o.value);
}

function applyTransform() {
  stage.style.transform = 'translate(' + panX + 'px,' + panY + 'px) scale(' + scale + ')';
}

function syncCanvas() {
  if (!img.naturalWidth) return;
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  canvas.style.width = img.naturalWidth + 'px';
  canvas.style.height = img.naturalHeight + 'px';
  redraw();
}

function redraw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  for (const g of guides) {
    const b = g.bbox;
    ctx.strokeStyle = g.was_uncertain ? '#c47a00' : '#4a90d9';
    ctx.lineWidth = 2 / scale;
    ctx.strokeRect(b.x * canvas.width, b.y * canvas.height, b.width * canvas.width, b.height * canvas.height);
    if (selectedGuide && selectedGuide.crop_id === g.crop_id) {
      ctx.fillStyle = 'rgba(74,144,217,0.15)';
      ctx.fillRect(b.x * canvas.width, b.y * canvas.height, b.width * canvas.width, b.height * canvas.height);
    }
  }
  if (draft) {
    ctx.strokeStyle = '#1b7f3a';
    ctx.lineWidth = 3 / scale;
    ctx.strokeRect(draft.x * canvas.width, draft.y * canvas.height, draft.width * canvas.width, draft.height * canvas.height);
  }
}

function toNorm(ev) {
  const rect = canvas.getBoundingClientRect();
  const x = (ev.clientX - rect.left) / rect.width;
  const y = (ev.clientY - rect.top) / rect.height;
  return { x: Math.min(1, Math.max(0, x)), y: Math.min(1, Math.max(0, y)) };
}

function warnGeometry(b) {
  const area = b.width * b.height;
  const msgs = [];
  if (area < 0.0001) msgs.push('Unusually small region');
  if (area > 0.35) msgs.push('Unusually broad region');
  warnEl.textContent = msgs.join(' · ');
}

async function loadNext() {
  const r = await fetch('/api/next?reviewer=' + encodeURIComponent(reviewer));
  const data = await r.json();
  guidesEl.innerHTML = '';
  selectedGuide = null;
  draft = null;
  warnEl.textContent = '';
  if (data.error) {
    statusEl.textContent = 'Error: ' + data.error;
    current = null;
    return;
  }
  const prog = data.progress || {};
  if (!data.opaque_page_reference) {
    statusEl.textContent = (data.message || 'Queue empty') +
      ' · seeds_active=' + (prog.seed_records_active ?? 0) +
      ' · pages_remaining=' + (prog.pages_remaining ?? 0);
    current = null;
    img.removeAttribute('src');
    syncCanvas();
    return;
  }
  current = data;
  statusEl.textContent = 'page=' + data.opaque_page_reference +
    ' · seeds_active=' + (prog.seed_records_active ?? 0) +
    ' · target=' + (prog.target_regions ?? 100) +
    ' · remaining_pages=' + (prog.pages_remaining ?? '?') +
    ' · reasons=' + ((data.priority_reasons || []).join(',') || 'n/a');
  guides = data.guides || [];
  for (const g of guides) {
    const div = document.createElement('div');
    div.className = 'guide' + (g.was_uncertain ? ' uncertain' : '');
    div.textContent = (g.was_uncertain ? 'uncertain-guide ' : 'guide ') + g.crop_id.slice(0, 18);
    div.onclick = () => {
      selectedGuide = g;
      Array.from(guidesEl.children).forEach(c => c.classList.remove('selected'));
      div.classList.add('selected');
      redraw();
    };
    guidesEl.appendChild(div);
  }
  img.onload = () => { syncCanvas(); scale = 1; panX = 0; panY = 0; applyTransform(); };
  img.src = '/api/page/' + encodeURIComponent(data.opaque_page_reference) + '?t=' + Date.now();
}

async function postSeed(body) {
  const r = await fetch('/api/seed', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok) {
    warnEl.textContent = data.error || 'request failed';
    return null;
  }
  if (data.geometry_warnings && data.geometry_warnings.length) {
    warnEl.textContent = data.geometry_warnings.join(' · ');
  }
  return data;
}

document.getElementById('confirmDraw').onclick = async () => {
  if (!current || !draft) { warnEl.textContent = 'Draw a region first'; return; }
  warnGeometry(draft);
  const body = {
    reviewer_id: reviewer,
    action: 'confirm_region',
    opaque_page_reference: current.opaque_page_reference,
    opaque_document_reference: current.opaque_document_reference,
    source_group_id: current.source_group_id,
    bbox: draft,
    categories: selectedCategories(),
  };
  if (selectedGuide) body.parent_crop_id = selectedGuide.crop_id;
  const data = await postSeed(body);
  if (!data) return;
  draft = null;
  await loadNext();
};

document.getElementById('confirmSelect').onclick = async () => {
  if (!current || !selectedGuide) { warnEl.textContent = 'Select an existing guide crop first'; return; }
  const data = await postSeed({
    reviewer_id: reviewer,
    action: 'select_existing_crop',
    opaque_page_reference: current.opaque_page_reference,
    opaque_document_reference: current.opaque_document_reference,
    source_group_id: current.source_group_id,
    parent_crop_id: selectedGuide.crop_id,
    categories: selectedCategories(),
  });
  if (!data) return;
  await loadNext();
};

document.getElementById('clearDraw').onclick = () => { draft = null; redraw(); warnEl.textContent = ''; };
document.getElementById('pageDone').onclick = async () => {
  if (!current) return;
  await postSeed({
    reviewer_id: reviewer,
    action: 'complete_page',
    opaque_page_reference: current.opaque_page_reference,
    opaque_document_reference: current.opaque_document_reference,
    source_group_id: current.source_group_id,
  });
  await loadNext();
};
document.getElementById('noHw').onclick = async () => {
  if (!current) return;
  await postSeed({
    reviewer_id: reviewer,
    action: 'no_usable_handwriting',
    opaque_page_reference: current.opaque_page_reference,
    opaque_document_reference: current.opaque_document_reference,
    source_group_id: current.source_group_id,
  });
  await loadNext();
};
document.getElementById('defer').onclick = async () => {
  if (!current) return;
  await postSeed({
    reviewer_id: reviewer,
    action: 'defer',
    opaque_page_reference: current.opaque_page_reference,
    opaque_document_reference: current.opaque_document_reference,
    source_group_id: current.source_group_id,
  });
  await loadNext();
};
document.getElementById('zoomIn').onclick = () => { scale = Math.min(6, scale * 1.25); applyTransform(); };
document.getElementById('zoomOut').onclick = () => { scale = Math.max(0.25, scale / 1.25); applyTransform(); };
document.getElementById('resetView').onclick = () => { scale = 1; panX = 0; panY = 0; applyTransform(); };

canvas.addEventListener('mousedown', (ev) => {
  if (!current) return;
  if (ev.button === 1 || spaceDown || ev.button === 2) {
    panning = true;
    panStart = { x: ev.clientX - panX, y: ev.clientY - panY };
    ev.preventDefault();
    return;
  }
  drawing = true;
  start = toNorm(ev);
  draft = null;
});
window.addEventListener('mousemove', (ev) => {
  if (panning && panStart) {
    panX = ev.clientX - panStart.x;
    panY = ev.clientY - panStart.y;
    applyTransform();
    return;
  }
  if (!drawing || !start) return;
  const cur = toNorm(ev);
  const x = Math.min(start.x, cur.x);
  const y = Math.min(start.y, cur.y);
  const width = Math.abs(cur.x - start.x);
  const height = Math.abs(cur.y - start.y);
  draft = { x, y, width, height };
  warnGeometry(draft);
  redraw();
});
window.addEventListener('mouseup', () => { drawing = false; panning = false; start = null; panStart = null; });
window.addEventListener('keydown', (ev) => { if (ev.code === 'Space') { spaceDown = true; ev.preventDefault(); } });
window.addEventListener('keyup', (ev) => { if (ev.code === 'Space') spaceDown = false; });
wrap.addEventListener('wheel', (ev) => {
  ev.preventDefault();
  const factor = ev.deltaY < 0 ? 1.1 : 0.9;
  scale = Math.min(6, Math.max(0.25, scale * factor));
  applyTransform();
}, { passive: false });
canvas.addEventListener('contextmenu', (ev) => ev.preventDefault());

if (!reviewer) {
  statusEl.textContent = 'Missing reviewer. Start with --reviewer and open the printed URL.';
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
    from backend.app.datasets.phase5.handwriting_seeds import (
        close_page,
        confirm_drawn_region,
        load_seed_queue,
        page_guide_crops,
        reviewer_id_ok,
        seed_page_state,
        seed_progress,
        select_existing_crop,
    )
    from backend.app.datasets.phase5.paths import pages_dir

    pages_root = pages_dir(private_root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("handwriting-seed: " + (fmt % args) + "\n")

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
            if not reviewer_id_ok(reviewer_id):
                return "reviewer_id must start with handwriting_reviewer_"
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
                queue = load_seed_queue(private_root)
                progress = seed_progress(private_root)
                if queue is None:
                    self._json(
                        200,
                        {
                            "opaque_page_reference": None,
                            "message": "No handwriting seed queue",
                            "progress": progress,
                        },
                    )
                    return
                closed = seed_page_state(private_root)
                remaining = [
                    e
                    for e in queue.entries
                    if closed.get(e.opaque_page_reference)
                    not in {"no_usable_handwriting", "defer", "complete_page"}
                ]
                if not remaining:
                    self._json(
                        200,
                        {
                            "opaque_page_reference": None,
                            "message": "Handwriting seed queue empty",
                            "progress": progress,
                        },
                    )
                    return
                entry = remaining[0]
                guides = page_guide_crops(private_root, entry.opaque_page_reference)
                self._json(
                    200,
                    {
                        "opaque_page_reference": entry.opaque_page_reference,
                        "opaque_document_reference": entry.opaque_document_reference,
                        "source_group_id": entry.source_group_id,
                        "priority_reasons": entry.priority_reasons,
                        "crop_count": entry.crop_count,
                        "uncertain_crop_count": entry.uncertain_crop_count,
                        "guides": guides,
                        "progress": progress,
                    },
                )
                return
            if parsed.path.startswith("/api/page/"):
                page_ref = parsed.path[len("/api/page/") :]
                if "/" in page_ref or ".." in page_ref or "\\" in page_ref:
                    self.send_error(400, "bad page ref")
                    return
                path = (pages_root / f"{page_ref}.png").resolve()
                if not str(path).startswith(str(pages_root.resolve())):
                    self.send_error(400, "path rejected")
                    return
                if not path.is_file():
                    self.send_error(404, "page missing")
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
            if parsed.path != "/api/seed":
                self.send_error(404, "not found")
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._json(400, {"error": "invalid json"})
                return
            # Reject leakage fields.
            for banned in (
                "text",
                "ocr_text",
                "transcript",
                "filename",
                "path",
                "prediction",
                "confidence",
            ):
                if banned in body:
                    self._json(400, {"error": f"forbidden field '{banned}'"})
                    return
            reviewer_id = str(body.get("reviewer_id") or "")
            err = self._check_reviewer(reviewer_id)
            if err:
                self._json(400, {"error": err})
                return
            action = str(body.get("action") or "")
            try:
                if action == "confirm_region":
                    result = confirm_drawn_region(
                        private_root=private_root,
                        opaque_page_reference=str(body["opaque_page_reference"]),
                        opaque_document_reference=str(body["opaque_document_reference"]),
                        source_group_id=str(body["source_group_id"]),
                        reviewer_id=reviewer_id,
                        bbox=dict(body["bbox"]),
                        parent_crop_id=body.get("parent_crop_id"),
                        categories=list(body.get("categories") or []),
                    )
                elif action == "select_existing_crop":
                    result = select_existing_crop(
                        private_root=private_root,
                        opaque_page_reference=str(body["opaque_page_reference"]),
                        opaque_document_reference=str(body["opaque_document_reference"]),
                        source_group_id=str(body["source_group_id"]),
                        reviewer_id=reviewer_id,
                        parent_crop_id=str(body["parent_crop_id"]),
                        categories=list(body.get("categories") or []),
                    )
                elif action in {"no_usable_handwriting", "defer", "complete_page"}:
                    result = close_page(
                        private_root=private_root,
                        opaque_page_reference=str(body["opaque_page_reference"]),
                        opaque_document_reference=str(body["opaque_document_reference"]),
                        source_group_id=str(body["source_group_id"]),
                        reviewer_id=reviewer_id,
                        action=action,
                    )
                else:
                    self._json(400, {"error": "unknown action"})
                    return
            except Exception as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(200, result)

    return Handler


def main(argv: list[str] | None = None) -> int:
    _ensure_repo_path()
    from backend.app.datasets.phase5.handwriting_seeds import reviewer_id_ok
    from backend.app.datasets.phase5.paths import default_private_root

    parser = argparse.ArgumentParser(description="Phase 5 loopback handwriting seed collector")
    parser.add_argument("--root", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument(
        "--reviewer",
        required=True,
        help="Opaque reviewer id (handwriting_reviewer_<id>)",
    )
    args = parser.parse_args(argv)
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("Refusing non-loopback bind", file=sys.stderr)
        return 2
    reviewer = str(args.reviewer).strip()
    if not reviewer_id_ok(reviewer):
        print("reviewer must start with handwriting_reviewer_", file=sys.stderr)
        return 2
    private_root = Path(args.root) if args.root else default_private_root()
    if not private_root.is_dir():
        print(f"Private root missing: {private_root}", file=sys.stderr)
        return 1
    handler = make_handler(private_root, expected_reviewer=reviewer)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        f"Phase 5 handwriting seed collection on "
        f"http://{args.host}:{args.port}/?reviewer={reviewer}"
    )
    print("Backup private manifests before long interruptions: pnpm phase5:dataset:backup")
    print("Confirm clear handwriting only. Do not transcribe. Target ~100 regions.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
