async function loadPages() {
  const status = document.getElementById("filter-status").value;
  const family = document.getElementById("filter-family").value;
  const route = document.getElementById("filter-route").value;
  const qs = new URLSearchParams();
  if (status) qs.set("status", status);
  if (family) qs.set("family", family);
  if (route) qs.set("route", route);
  const res = await fetch("/api/pages?" + qs.toString());
  const data = await res.json();
  const tbody = document.querySelector("#pages-table tbody");
  tbody.innerHTML = "";
  document.getElementById("count").textContent = `${data.count} pages`;
  for (const p of data.pages || []) {
    const tr = document.createElement("tr");
    const machine = [
      p.has_render ? "render" : "",
      p.has_native ? "native" : "",
      p.has_ocr ? "ocr" : "",
    ]
      .filter(Boolean)
      .join(", ") || "—";
    tr.innerHTML = `
      <td>${esc(p.case_alias)}</td>
      <td>${esc(p.doc_alias)}</td>
      <td>${p.page_number ?? ""}</td>
      <td>${esc((p.challenges || []).join(", "))}</td>
      <td>${esc(machine)}</td>
      <td><span class="badge ${esc(p.annotation_status)}">${esc(p.annotation_status)}</span></td>
      <td>${esc(p.critical_anchor_status)}</td>
      <td>${p.text_review_complete ? "✓" : "—"}</td>
      <td>${p.order_review_complete ? "✓" : "—"}</td>
      <td>${p.geometry_review_complete ? "✓" : "—"}</td>
      <td><a href="/page.html?page_id=${encodeURIComponent(p.page_id)}">Open</a></td>`;
    tbody.appendChild(tr);
  }
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

document.getElementById("apply-filters").addEventListener("click", loadPages);
loadPages();
