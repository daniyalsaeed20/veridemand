# Phase 2 Hardening Report — B-01 / B-02

**Status date:** 2026-07-20  
**Branch:** `phase-02-audit-hardening`  
**Hardening verdict:** **READY FOR RE-AUDIT** (do not create `phase-02-audited-pass` until independent re-audit)

---

## 1. Baseline and evidence commits

| Field | Value |
|-------|-------|
| Phase 1 audited baseline | `phase-01-audited-pass` → `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093` |
| Phase 2 implementation | `359dab1429e2549b6e6bab9d3cf24ae279ad1cf1` |
| Audited tip (FAIL audit) | `f6c675f215e04877a97de89358ae515e3efa538a` |
| Audit evidence commit | `e358d72` — `docs: record Phase 2 independent audit FAIL` |
| Prior audit | [`phase-02-audit.md`](./phase-02-audit.md) — **FAIL** (B-01, B-02) |

Scope constraint honored: no Phase 3 OCR, no PaddleOCR, no classification/facts/chronology/billing interpretation/issues/LLM/drafting/export.

---

## 2. B-01 — PDFium process-wide boundary

### Design

- New sole importer: [`backend/app/services/documents/pdfium_runtime.py`](../../backend/app/services/documents/pdfium_runtime.py)
- Process-wide `threading.RLock` (`_PDFIUM_LOCK`) shared by all service instances/sessions
- Public ops: `count_pages`, `render_all_pages`, `render_page`
- Native `PdfDocument` / page / bitmap handles never escape the critical section
- Close via `try/finally`; exceptions release the lock via context manager
- Thumbnail resize/PNG save runs **outside** the lock after detached PIL copies

### Call-site inventory (application)

| Site | Role after hardening |
|------|----------------------|
| `pdfium_runtime.py` | **Only** `import pypdfium2` |
| `thumbnails.py` | Calls runtime only (no direct pypdfium2) |
| `process/service.py` | Unchanged API: `count_pdf_pages` / `create_thumbnails` |

Architectural enforcement: [`test_pdfium_import_boundary.py`](../../backend/tests/unit/test_pdfium_import_boundary.py) AST-scans `backend/app` and fails on any other `pypdfium2` import.

### Concurrency evidence

| Test | Result |
|------|--------|
| Concurrent thumbnails (2 docs) | max inflight == 1 |
| Count overlaps render | max inflight == 1 |
| Four-way contention | max inflight == 1 |
| Exception releases mutex; subsequent work OK | PASS |
| Cancel simulation (`InterruptedError`) does not permanently lock | PASS |
| Separate callers share same lock object | PASS |
| Two sessions concurrent `POST /process` | both 200; max inflight == 1 |
| Local real-pypdfium2 stress (billing + police thumbs) | max inflight == 1 |

---

## 3. B-02 — Native usability quality gate

### Design

Extended [`routing.py`](../../backend/app/services/extraction/routing.py) with multi-signal diagnostics:

- mean / median / max token length; long-token ratio (band)
- replacement / control / printable ratios
- CID markers, private-use glyphs, repeated-glyph anomalies
- zero-width/overlap and oversized-box geometry
- reading-order (existing)

**Pathological tokenization** (composite, not max-length alone):

1. `long_token_ratio > max` AND (`mean > max_mean` OR `median > max_median`), or  
2. `mean > max_mean` AND `median > max_median` (dual elevation / missing-space pages)

On failure: `PageRoute.ocr`, flags `pathological_tokenization` + `broken_text_layer` + `awaiting_ocr` (at extract), **zero** published SourceTokens/SourceSpans. Not treated as blank. No PaddleOCR.

### Provisional thresholds (`0.1-provisional`)

Documented in [`app-settings.md`](../contracts/entities/app-settings.md) and [`03-ocr-thresholds.md`](../modules/03-ocr-thresholds.md):

| Setting | Default |
|---------|---------|
| `native_long_token_band` | 40 |
| `native_max_long_token_ratio` | 0.20 |
| `native_max_mean_token_length` | 24 |
| `native_max_median_token_length` | 18 |
| `native_min_printable_ratio` | 0.90 |
| `native_max_control_char_ratio` | 0.02 |
| `native_max_oversized_box_ratio` | 0.20 |

### Synthetic fixture results

[`test_native_usability_gate.py`](../../backend/tests/unit/test_native_usability_gate.py): pathological missing-space, CID-like, extreme long tokens → OCR; prose, dense table, single long URL, long identifier, mixed → native; blank → manual_review; sparse/scan → OCR. No PaddleOCR imports in extraction package.

---

## 4. Local reference-package results (aliases/hashes only)

| Alias | SHA16 | Pages | Native / OCR / MR | Published tokens/spans | Notes |
|-------|-------|-------|-------------------|------------------------|-------|
| `ecw_billing` | `167b9052da1b662e` | 1 | 0 / **1** / 0 | **0 / 0** | pathological; mean≈30.0; max_len=450 |
| `ecw_medical` | `9fc3d498462cb55a` | 24 | **24** / 0 / 0 | 7679 / 1003 | unchanged strong native |
| `police_like` | `797da053c3a988c5` | 4 | 3 / 1 / 0 | 935 / 275 | |
| `insurer_scan` | `8212e9d305a0bae1` | 1 | 1 / 0 / 0 | 208 / 45 | usable native layer on this sample |

**eCW billing (B-02 closure):**

- Page count: 1  
- Native unusable / OCR-pending: 1  
- Pre-suppression diagnostics (safe): mean token length ≈ 30.02; max token length 450  
- Published usable tokens/spans after fix: **0 / 0**  
- Duration: ~0.4s  

---

## 5. API / frontend

- OCR-pending pages already surface `ocr_status=pending` and “awaiting Phase 3 OCR” in `DocumentViewer`
- Tokens/spans endpoints return empty lists when none stored (OCR route publishes none)
- Viewing PDF + thumbnails remain available
- AppSettings schema regenerated; contracts drift check OK
- No OCR overlays implemented

---

## 6. Regression totals

`node scripts/check-all.mjs` (2026-07-20):

| Gate | Result |
|------|--------|
| ruff format/check | PASS |
| mypy strict | PASS (67 source files) |
| pytest | **129 passed** |
| contracts generate + drift + proof | PASS |
| FE prettier / eslint / tsc | PASS |
| vitest | **9 passed** |
| production build | PASS (PDF.js chunk warning unchanged) |

Contract regen ×2 via check-contracts: no drift.

---

## 7. Contract changes

- Additive `AppSettings` fields for pathological tokenization knobs  
- `DocumentPage.quality_flags` notes: `pathological_tokenization`, `awaiting_ocr`  
- Thresholds addendum updated; still `0.1-provisional` / OD-01 open for broader calibration  

---

## 8. Remaining limitations

1. Provisional thresholds — not firm-calibrated general OCR accuracy (OD-01).  
2. Some scan-like pages with a usable text layer may still score native (e.g. insurer sample).  
3. LibreOffice / browser visual highlight gaps from the FAIL audit are unchanged (out of B-01/B-02 scope).  
4. Mid-request PDFium cancel is simulated via exception hooks (no async cancel API in Phase 2).  
5. Do **not** treat this report as an audited PASS tag.

---

## 9. Final hardening verdict

**B-01 and B-02 closed with automated + local reference evidence.**

Request a **fresh independent re-audit** of the hardening tip.  
Do **not** create `phase-02-audited-pass` until that re-audit.  
Do **not** begin Phase 3.
