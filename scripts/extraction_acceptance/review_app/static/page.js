/* global ReviewOverlay */

const QUESTIONS = [
  ["text_matches_visible_page", "Does the extracted text match the page?"],
  ["words_missing", "Are visible words missing?"],
  ["extra_words_present", "Are words present that do not appear on the page?"],
  ["reading_order_correct", "Is the text in the correct reading order?"],
  ["boxes_enclose_correct_words", "Do the boxes surround the correct visible words?"],
  ["native_text_layer_trustworthy", "Can the existing PDF text layer be trusted?"],
  ["fresh_ocr_required", "Should fresh OCR be used?"],
  ["page_unreadable", "Is any part of the page unreadable?"],
  ["critical_values_exact", "Are the listed important values exact?"],
];

const ANSWERS = ["", "Yes", "No", "Partly", "Not applicable", "Unsure"];

const state = {
  pageId: null,
  annotation: null,
  nav: null,
  img: null,
  scale: 1,
  panX: 0,
  panY: 0,
  overlays: { native: [], ocr: [], tokens: [], spans: [], human: [] },
  drawing: false,
  dragStart: null,
  hitItems: [],
};

function qs(name) {
  return new URLSearchParams(location.search).get(name);
}

function $(id) {
  return document.getElementById(id);
}

async function init() {
  state.pageId = qs("page_id");
  if (!state.pageId) {
    $("save-msg").textContent = "Missing page_id";
    return;
  }
  renderQuestions();
  await loadPage();
  wire();
}

function renderQuestions() {
  const root = $("questions");
  root.innerHTML = "";
  for (const [key, label] of QUESTIONS) {
    const div = document.createElement("div");
    div.className = "q-row";
    div.innerHTML = `<span>${label}</span>`;
    const sel = document.createElement("select");
    sel.dataset.q = key;
    for (const a of ANSWERS) {
      const opt = document.createElement("option");
      opt.value = a;
      opt.textContent = a || "— select —";
      sel.appendChild(opt);
    }
    div.appendChild(sel);
    root.appendChild(div);
  }
}

async function loadPage() {
  const res = await fetch(`/api/pages/${encodeURIComponent(state.pageId)}`);
  if (!res.ok) {
    $("save-msg").textContent = "Failed to load page";
    return;
  }
  const data = await res.json();
  state.annotation = data.annotation;
  state.nav = data.nav;
  $("page-title").textContent = `${state.annotation.case_alias} / ${state.annotation.doc_alias} p${state.annotation.page_number}`;
  $("status-badge").textContent = state.annotation.annotation_status;
  $("status-badge").className = "badge " + state.annotation.annotation_status;
  $("nav-info").textContent = state.nav
    ? `${(state.nav.index ?? 0) + 1} / ${state.nav.total}`
    : "";
  $("machine-transcript").value = state.annotation.machine_transcript || "";
  $("expected-transcript").value = state.annotation.expected_transcript || "";
  $("order-confirmed").checked = !!state.annotation.reading_order_confirmed;
  $("order-complete").checked = !!state.annotation.order_review_complete;
  $("geom-complete").checked = !!state.annotation.geometry_review_complete;
  $("text-complete").checked = !!state.annotation.text_review_complete;
  $("reviewer").value = state.annotation.reviewer || "";
  $("review-date").value = state.annotation.review_date || "";
  $("notes").value = state.annotation.notes || "";

  const qsMap = state.annotation.questions || {};
  for (const sel of document.querySelectorAll("#questions select")) {
    sel.value = qsMap[sel.dataset.q] || "";
  }
  const flags = new Set(state.annotation.order_issue_flags || []);
  for (const cb of document.querySelectorAll(".flags input[data-flag]")) {
    cb.checked = flags.has(cb.dataset.flag);
  }

  renderOrder();
  renderCritical();
  renderHumanBoxes();
  await loadOverlays();
  await loadImage();
}

function renderOrder() {
  const list = $("order-list");
  list.innerHTML = "";
  const items =
    (state.annotation.expected_reading_order && state.annotation.expected_reading_order.length
      ? state.annotation.expected_reading_order
      : state.annotation.machine_reading_order) || [];
  items.forEach((it, idx) => {
    const li = document.createElement("li");
    li.draggable = true;
    li.dataset.idx = String(idx);
    li.textContent = `${idx + 1}. ${(it.text || "").slice(0, 80)}`;
    li.addEventListener("dragstart", (e) => {
      li.classList.add("dragging");
      e.dataTransfer.setData("text/plain", String(idx));
    });
    li.addEventListener("dragend", () => li.classList.remove("dragging"));
    li.addEventListener("dragover", (e) => e.preventDefault());
    li.addEventListener("drop", (e) => {
      e.preventDefault();
      const from = Number(e.dataTransfer.getData("text/plain"));
      const to = Number(li.dataset.idx);
      reorder(from, to);
    });
    list.appendChild(li);
  });
  if (!state.annotation.expected_reading_order || !state.annotation.expected_reading_order.length) {
    state.annotation.expected_reading_order = JSON.parse(JSON.stringify(items));
  }
}

function reorder(from, to) {
  const arr = state.annotation.expected_reading_order || [];
  if (from === to || from < 0 || to < 0 || from >= arr.length || to >= arr.length) return;
  const [item] = arr.splice(from, 1);
  arr.splice(to, 0, item);
  arr.forEach((x, i) => (x.reading_order = i));
  renderOrder();
}

function renderCritical() {
  const root = $("critical-fields");
  root.innerHTML = "";
  for (const f of state.annotation.critical_fields || []) {
    const div = document.createElement("div");
    div.className = "crit";
    div.innerHTML = `
      <strong>${esc(f.friendly_name || f.field_id)}</strong>
      <div>Expected: <code>${esc(f.expected)}</code></div>
      ${f.corrupt_embedded_candidate ? `<div>Corrupt embed: <code>${esc(f.corrupt_embedded_candidate)}</code></div>` : ""}
      <label>Machine reading <input data-cf="${esc(f.field_id)}" data-k="machine_reading" value="${esc(f.machine_reading || "")}"/></label>
      <label>Layer <input data-cf="${esc(f.field_id)}" data-k="layer" value="${esc(f.layer || "")}"/></label>
      <label>Resolution
        <select data-cf="${esc(f.field_id)}" data-k="status">
          <option value="USER_CONFIRMED_ANCHOR">Unresolved anchor</option>
          <option value="exact">Exact</option>
          <option value="incorrect">Incorrect</option>
          <option value="unreadable">Unreadable</option>
        </select>
      </label>
      <label>Notes <input data-cf="${esc(f.field_id)}" data-k="notes" value="${esc(f.notes || "")}"/></label>
    `;
    root.appendChild(div);
    const sel = div.querySelector("select");
    sel.value = ["exact", "incorrect", "unreadable"].includes(f.status)
      ? f.status
      : f.match_status && ["exact", "incorrect", "unreadable"].includes(f.match_status)
        ? f.match_status
        : "USER_CONFIRMED_ANCHOR";
  }
}

function renderHumanBoxes() {
  const ul = $("human-boxes");
  ul.innerHTML = "";
  (state.annotation.expected_boxes || []).forEach((b, i) => {
    const li = document.createElement("li");
    li.textContent = `${b.box_id || i}: ${b.granularity} [${b.status || "draft"}] ${b.associated_text || ""}`;
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "Delete";
    del.onclick = () => {
      state.annotation.expected_boxes.splice(i, 1);
      renderHumanBoxes();
      redraw();
    };
    li.appendChild(del);
    ul.appendChild(li);
  });
  state.overlays.human = state.annotation.expected_boxes || [];
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/"/g, "&quot;");
}

async function loadOverlays() {
  state.overlays.native = await fetchOverlay("native_words", "words");
  const lines = await fetchOverlay("ocr_lines", "lines");
  state.overlays.ocr = lines;
  state.overlays.tokens = await fetchOverlay("source_tokens", null);
  state.overlays.spans = await fetchOverlay("source_spans", null);
  state.overlays.human = state.annotation.expected_boxes || [];
  rebuildHitItems();
}

async function fetchOverlay(layer, key) {
  const res = await fetch(`/api/pages/${encodeURIComponent(state.pageId)}/overlays/${layer}`);
  if (!res.ok) return [];
  const data = await res.json();
  if (Array.isArray(data)) return data;
  if (key && Array.isArray(data[key])) return data[key];
  if (Array.isArray(data.items)) return data.items;
  return [];
}

function rebuildHitItems() {
  const items = [];
  const push = (arr, layer) => {
    for (const it of arr || []) {
      if (!it.polygon) continue;
      items.push({ ...it, layer, granularity: it.granularity || (layer === "ocr" ? "line" : "word") });
    }
  };
  if ($("ov-native").checked) push(state.overlays.native, "native");
  if ($("ov-ocr").checked) push(state.overlays.ocr, "ocr");
  if ($("ov-tokens").checked) push(state.overlays.tokens, "token");
  if ($("ov-spans").checked) push(state.overlays.spans, "span");
  if ($("ov-human").checked) push(state.overlays.human, "human");
  state.hitItems = items;
}

async function loadImage() {
  const img = new Image();
  img.onload = () => {
    state.img = img;
    const canvas = $("canvas");
    canvas.width = img.width;
    canvas.height = img.height;
    redraw();
  };
  img.onerror = () => {
    $("token-info").textContent = "No page render available for this page.";
  };
  img.src = `/api/pages/${encodeURIComponent(state.pageId)}/render?` + Date.now();
}

function redraw() {
  const canvas = $("canvas");
  const ctx = canvas.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.setTransform(state.scale, 0, 0, state.scale, state.panX, state.panY);
  if (state.img) ctx.drawImage(state.img, 0, 0);
  const w = canvas.width;
  const h = canvas.height;
  const O = window.ReviewOverlay;
  rebuildHitItems();
  const styles = {
    native: { stroke: "#22c55e", fill: "rgba(34,197,94,0.12)" },
    ocr: { stroke: "#3b82f6", fill: "rgba(59,130,246,0.12)" },
    token: { stroke: "#a855f7", fill: "rgba(168,85,247,0.1)" },
    span: { stroke: "#f59e0b", fill: "rgba(245,158,11,0.1)" },
    human: { stroke: "#ef4444", fill: "rgba(239,68,68,0.15)", width: 2 },
  };
  for (const it of state.hitItems) {
    const pts = O.normToCanvas(it.polygon, w, h);
    O.drawPolygon(ctx, pts, styles[it.layer] || styles.native);
    if ($("ov-order").checked && it.reading_order != null && pts[0]) {
      ctx.fillStyle = "#fff";
      ctx.font = "14px sans-serif";
      ctx.fillText(String(it.reading_order), pts[0][0], pts[0][1] - 2);
    }
  }
}

function collectAnnotation() {
  const a = state.annotation;
  a.expected_transcript = $("expected-transcript").value;
  a.reading_order_confirmed = $("order-confirmed").checked;
  a.order_review_complete = $("order-complete").checked;
  a.geometry_review_complete = $("geom-complete").checked;
  a.text_review_complete = $("text-complete").checked;
  a.reviewer = $("reviewer").value.trim();
  a.review_date = $("review-date").value;
  a.notes = $("notes").value;
  a.questions = a.questions || {};
  for (const sel of document.querySelectorAll("#questions select")) {
    a.questions[sel.dataset.q] = sel.value;
  }
  a.order_issue_flags = [];
  for (const cb of document.querySelectorAll(".flags input[data-flag]")) {
    if (cb.checked) a.order_issue_flags.push(cb.dataset.flag);
  }
  for (const el of document.querySelectorAll("#critical-fields [data-cf]")) {
    const id = el.dataset.cf;
    const k = el.dataset.k;
    const field = (a.critical_fields || []).find((f) => f.field_id === id);
    if (field) {
      field[k] = el.value;
      if (k === "status" && ["exact", "incorrect", "unreadable"].includes(el.value)) {
        field.match_status = el.value;
      }
    }
  }
  return a;
}

async function save() {
  const payload = collectAnnotation();
  const res = await fetch(`/api/pages/${encodeURIComponent(state.pageId)}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "If-Match": payload.etag || "",
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) {
    $("save-msg").textContent = JSON.stringify(data, null, 2);
    return false;
  }
  state.annotation = data;
  $("status-badge").textContent = data.annotation_status;
  $("save-msg").textContent = `Saved revision ${data.revision}`;
  return true;
}

async function markReviewed(second) {
  collectAnnotation();
  const body = { ...state.annotation, needs_second_review: !!second };
  const res = await fetch(`/api/pages/${encodeURIComponent(state.pageId)}/mark-reviewed`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    $("save-msg").textContent = "Blocked:\n" + JSON.stringify(data, null, 2);
    return;
  }
  state.annotation = data;
  $("status-badge").textContent = data.annotation_status;
  $("save-msg").textContent = `Marked ${data.annotation_status}`;
}

function wire() {
  $("zoom-in").onclick = () => {
    state.scale *= 1.2;
    redraw();
  };
  $("zoom-out").onclick = () => {
    state.scale /= 1.2;
    redraw();
  };
  $("zoom-reset").onclick = () => {
    state.scale = 1;
    state.panX = 0;
    state.panY = 0;
    redraw();
  };
  for (const id of ["ov-native", "ov-ocr", "ov-tokens", "ov-spans", "ov-human", "ov-order"]) {
    $(id).onchange = () => redraw();
  }
  $("copy-machine").onclick = () => {
    $("expected-transcript").value = $("machine-transcript").value;
  };
  $("reset-prefill").onclick = () => {
    if (state.annotation.annotation_status === "human_reviewed") {
      if (!confirm("Clear expected transcript? Previously saved human text will be lost on next save.")) return;
    }
    $("expected-transcript").value = "";
  };
  $("draw-toggle").onclick = () => {
    state.drawing = !state.drawing;
    $("viewer").classList.toggle("drawing", state.drawing);
    $("draw-toggle").textContent = state.drawing ? "Cancel draw" : "Draw box";
  };
  $("btn-save").onclick = () => save();
  $("btn-save-next").onclick = async () => {
    if (await save()) goNav("next");
  };
  $("btn-prev").onclick = () => goNav("prev");
  $("btn-next").onclick = () => goNav("next");
  $("btn-mark").onclick = () => markReviewed(false);
  $("btn-second").onclick = () => markReviewed(true);

  const canvas = $("canvas");
  let panning = false;
  let last = null;
  canvas.addEventListener("mousedown", (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX - rect.left - state.panX) / state.scale;
    const y = (e.clientY - rect.top - state.panY) / state.scale;
    if (state.drawing) {
      state.dragStart = { x, y };
      return;
    }
    const hit = window.ReviewOverlay.hitTest(state.hitItems, x, y, canvas.width, canvas.height);
    if (hit) {
      $("token-info").textContent = JSON.stringify(
        {
          text: hit.text,
          layer: hit.layer,
          confidence: hit.confidence,
          reading_order: hit.reading_order,
          granularity: hit.granularity,
        },
        null,
        2
      );
    } else {
      panning = true;
      last = { x: e.clientX, y: e.clientY };
    }
  });
  canvas.addEventListener("mousemove", (e) => {
    if (panning && last) {
      state.panX += e.clientX - last.x;
      state.panY += e.clientY - last.y;
      last = { x: e.clientX, y: e.clientY };
      redraw();
    }
  });
  window.addEventListener("mouseup", (e) => {
    if (state.drawing && state.dragStart) {
      const rect = canvas.getBoundingClientRect();
      const x = (e.clientX - rect.left - state.panX) / state.scale;
      const y = (e.clientY - rect.top - state.panY) / state.scale;
      const poly = window.ReviewOverlay.canvasToNorm(
        state.dragStart.x,
        state.dragStart.y,
        x,
        y,
        canvas.width,
        canvas.height
      );
      const gran = $("draw-granularity").value;
      const box = {
        box_id: "hb_" + Date.now(),
        granularity: gran,
        polygon: poly,
        associated_text: "",
        status: "draft",
      };
      state.annotation.expected_boxes = state.annotation.expected_boxes || [];
      state.annotation.expected_boxes.push(box);
      state.dragStart = null;
      state.drawing = false;
      $("viewer").classList.remove("drawing");
      $("draw-toggle").textContent = "Draw box";
      renderHumanBoxes();
      redraw();
      return;
    }
    panning = false;
    last = null;
  });
}

function goNav(dir) {
  const id = state.nav && state.nav[dir];
  if (id) location.href = `/page.html?page_id=${encodeURIComponent(id)}`;
}

init();
