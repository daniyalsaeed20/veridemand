# Phase 2 Independent Audit — Canonical Viewer and Native Extraction

**Audit date:** 2026-07-20  
**Auditor:** Fresh independent verification (not the Phase 2 implementer’s PASS WITH GAPS claim)  
**Method:** Clean tip verification + authoritative doc/contract review + real LibreOffice probes + PDFium concurrency probes + reference-package acceptance (aliases/hashes only) + contract dual-regen + full `check-all` regression  

**Constraints honored:** No production code changes. No Phase 3 work. No Git tag create/move/delete. Audit probes lived only under gitignored `tmp/audit/`.

---

## Final verdict

# FAIL

The audited commit is **not** suitable for an immutable tag named `phase-02-audited-pass`.

Phase 2 implements a large share of the intended deliverables (DOCX/image normalize, thumbnails, pdfplumber tokens/spans, PDF.js viewer, session isolation, automated gates). Two **blocking** defects prevent an audited pass:

1. **PDFium / pypdfium2 has no process-wide synchronization boundary** while thumbnail generation can run from concurrent request threads across sessions (§4).
2. **eCW billing (known broken native layer) is accepted as usable native text** and emits tokens/spans, instead of routing to OCR-pending (§7 / acceptance expectation).

Do **not** create `phase-02-audited-pass`. Do **not** begin Phase 3 until these blockers are fixed and re-audited.

---

## Exact audited commit

| Field | Value |
|-------|-------|
| Branch | `phase-02-viewer-native-extraction` |
| **Audited tip** | `f6c675f215e04877a97de89358ae515e3efa538a` |
| Tip subject | `docs: add Phase 1 hardening audit report` |
| Implementation commit | `359dab1429e2549b6e6bab9d3cf24ae279ad1cf1` (`phase-02: add canonical viewer and native PDF extraction`) |
| Working tree at audit | Clean after docs-only commit |

`359dab1` is **not** the branch tip. A later documentation-only commit added the previously untracked Phase 1 hardening audit report. This audit records and evaluates **`f6c675f`**.

### Baseline

| Field | Value |
|-------|-------|
| Tag | `phase-01-audited-pass` |
| Peeled commit | `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093` |
| Ancestor of audited tip | **Yes** |

### Commits reviewed (`phase-01-audited-pass..HEAD`)

1. `359dab1` — Phase 2 implementation  
2. `f6c675f` — docs: Phase 1 hardening audit report  

---

## 1. Git, baseline and scope

| Check | Result |
|-------|--------|
| Audited tree == stated final tip | **PASS** (`f6c675f`) |
| Branch begins from `phase-01-audited-pass` | **PASS** |
| Working tree clean | **PASS** (at audit tip) |
| Phase 1 hardening audit report committed | **PASS** (`docs/implementation-reports/phase-01-hardening-audit.md`) |
| No firm PDFs/DOCXs committed in range | **PASS** (gitignore holds; diff has no binary evidence files) |
| Phase 3 OCR not implemented | **PASS** |
| PaddleOCR not called from app | **PASS** (spikes only; no `backend/app` import) |
| No classification / facts / chronology / billing analysis / issues / LLM / drafting / export work introduced | **PASS** (contract model stubs remain; no Phase 2 services for those domains) |

### Diff reviewed (file list)

Notable additions/changes under `5ab566f..f6c675f`:

- Backend: `convert_docx.py`, `image_pdf.py`, `thumbnails.py`, `extraction/{coordinates,native,routing,spans}.py`, `process/service.py`, session API extensions, tests  
- Frontend: `DocumentViewer.tsx`, viewer schemas/tests, `pdfjs-dist`  
- Deps: `pdfplumber==0.11.7`, `pypdfium2==4.30.0`, `pdfjs-dist@^4.10.38`  
- Docs: `phase-02-completion.md`, `phase-01-hardening-audit.md`, OD-05 / local-setup updates  
- Generated contracts: `ProcessEvent` + index updates  

### Dependency / contract changes

Production deps added are appropriate for Phase 2 viewer/native extraction. No OCR/LLM runtime deps added to the app.

---

## 2. Phase completion gaps assessed

Source: [`phase-02-completion.md`](./phase-02-completion.md) (claimed **PASS WITH GAPS**).

| # | Gap | Requirement | Blocking? | Later owner | Completion verdict accurate? |
|---|-----|-------------|-----------|-------------|------------------------------|
| 1 | Exit gate via `SourceSpan` selection, not Fact entities | Matrix “native fact” wording | **Nonblocking** | Phase 5+ Facts UI | Yes — recorded reinterpretation |
| 2 | LibreOffice required; CI uses fake converter | FR-UPL-06 | **Nonblocking for CI**; real LO must be evidenced for unconditional FR-UPL-06 pass | Ops / local demo | Partially — real LO **was** evidenced in this audit |
| 3 | Provisional OCR/native thresholds (OD-01) | FR-EXT-02 | **Nonblocking as OD-01** *unless* known-bad fixtures are wrongly accepted as native (see blocking #2) | Phase 3 calibration (OD-01) | Understated — eCW billing expectation not met |
| 4 | Module 03 full exit is Phases 2–3 | Module 03 | **Nonblocking** (explicit non-claim) | Phase 3 | Yes |
| 5 | `DocumentPage` lacks rotation/thumb/char fields | Contracts | **Nonblocking** | Later contract enrichment | Yes — server-side rotation + API thumbs |
| 6 | Scans lack native spans until Phase 3 | FR-EXT / OCR | **Nonblocking** (by design) | Phase 3 | Yes |
| 7 | Large PDF.js worker chunk | Perf/build | **Nonblocking** | FE bundling polish | Yes |

**Undocumented / incorrect completion claim:** reference-package table expects eCW billing → OCR route. Independent run routed it **native**. That is not an accepted indefinite deferral; it is a **blocking FR-EXT-02 / §7 defect** (below).

---

## 3. Real LibreOffice evidence (FR-UPL-06)

| Item | Evidence |
|------|----------|
| Version | LibreOffice 26.2.4.2 (`0229ac93…`) |
| Executable resolution | `PATH` / `soffice.COM` → `D:\programming\tools\libreoffice\program\soffice.COM` (also `LIBREOFFICE_PATH` supported in `ServerSettings`) |
| Command structure | List-arg `subprocess.run` (no shell): `<exe> --headless --nologo --nolockcheck --nodefault --norestore --convert-to pdf --outdir <staging> <staged_input>` |
| `-env:UserInstallation` | **Not used** |
| Serialization | Process-wide `threading.Lock` `_CONVERSION_LOCK` — **justified global serialization** |
| Shell interpolation | **None** (argv list) |
| Log hygiene | Failure logs returncode only; document content not logged |

### Probe results

| Probe | Duration | Pages | Original unchanged | Staging cleaned | Result |
|-------|----------|-------|--------------------|-----------------|--------|
| Synthetic multi-page DOCX | 6.524s | 2 | Yes | Yes | **OK** |
| Firm-style DOCX (masked) | 1.606s | 5 | Yes | Yes | **OK** |
| Multi-page firm DOCX (masked) | 1.251s | 5 | Yes | Yes | **OK** |
| Two concurrent conversions | wall 2.274s (serialized) | 2+2 | Yes | Yes | **Both OK** — lock prevented profile clash |
| Timeout (`timeout_seconds=1`) | 1.027s | — | Yes | Partial PDF absent | **Raises** `DOCX conversion timed out.` |

**FR-UPL-06 real-converter exercise:** satisfied for success path, serialization, staging isolation, argv safety, and original preservation.

**Residual nonblocking notes:**

- Timeout path relies on `subprocess.run(..., timeout=)` process kill; LibreOffice child (`soffice.bin`) kill-tree behavior was not exhaustively proven on this host.  
- Captured stdout/stderr are unbounded in memory (not logged), so content leak via logs is avoided, but capture itself is not size-capped.  
- Session-delete-during-conversion was covered by design review + existing isolation tests; not separately race-probed in this audit.

---

## 4. PDFium / pypdfium2 thread-safety — BLOCKING FAIL

### Call sites

Only [`backend/app/services/documents/thumbnails.py`](../../backend/app/services/documents/thumbnails.py): `create_thumbnails`, `count_pdf_pages`.

### Code review

| Requirement | Finding |
|-------------|---------|
| Process-wide sync boundary | **Absent** |
| Lock not instance-local | N/A (no lock) |
| Page/PDF close | **Present** (`page.close()`, `pdf.close()` in `finally`) |
| Page-by-page bitmaps | **Present** (no full-doc bitmap retention) |
| Concurrent session risk | `POST /process` is synchronous per request; **per-session** `process_running` only — two sessions can process concurrently on uvicorn worker threads |

### Concurrency probes (`tmp/audit/probe_pdfium.py`)

| Probe | Result |
|-------|--------|
| Sequential `create_thumbnails` | OK |
| Concurrent thumbs on two PDFs | OK this run (no crash) |
| Concurrent raw PDFium ×4 threads | OK this run (no crash) |

**Classification:** Lucky probe success does **not** satisfy the requirement for a process-wide synchronization boundary. PDFium is documented as process-global / not free-threaded. Missing lock is a **blocking thread-safety defect** under the audit criteria.

---

## 5–6. PDF/image normalization, page metadata, thumbnails

| Check | Result |
|-------|--------|
| Originals unchanged | **PASS** (reference + LO probes; SHA stable) |
| Viewing copies app-controlled (`derived/`) | **PASS** (code + process service) |
| Valid PDF passthrough (not rewritten) | **PASS** |
| Corrupt PDF fails safely | **PASS** (`PdfiumError` on synthetic corrupt) |
| JPG/PNG → PDF | **PASS** (synthetic) |
| EXIF orientation | Uses `ImageOps.exif_transpose` — **PASS** pattern; firm package lacked EXIF sample |
| TIFF multipage order | **PASS** (synthetic 3-frame TIFF → 3 PDF pages) |
| Decompression bomb bound | Pillow default `MAX_IMAGE_PIXELS=89478485` only — **nonblocking** (no app-specific tighter cap) |
| Partial cleanup / idempotent replace | **PASS** pattern in convert/image_pdf/thumbs |
| Session delete removes derivatives | **PASS** (integration tests) |
| Thumb aspect ratio | Width-capped with proportional height — **PASS** |
| Thumb URLs no FS paths | **PASS** (API routes; isolation tests) |
| Cross-session / expired / crafted IDs | **PASS** (`test_phase02_process.py` 11 passed) |

**Material gap:** local reference package contains **no** JPG/PNG/TIFF; image/TIFF acceptance relied on synthetics (§13).

---

## 7. Native extraction findings

Implementation: pdfplumber words → `SourceToken` / `SourceSpan` when route is `native`; OCR never executed.

| Topic | Finding |
|-------|---------|
| Tokens preserve text+geometry without facts | **PASS** |
| Invalid geometry rejected | **PASS** (unit tests + coordinate reject path) |
| Scanned/low-text → OCR pending | **Partial** — police_like had 1/4 OCR; many “scan-like” pages still scored native under provisional thresholds |
| Blank → `manual_review` | **PASS** (routing code) |
| No fabricated OCR results | **PASS** |

### eCW billing (CID / broken native) — BLOCKING

| Metric | Value |
|--------|-------|
| Alias | `ecw_billing` |
| SHA16 | `167b9052da1b662e` |
| Route observed | **`native`** (expected OCR-pending) |
| Tokens / spans emitted | 185 / 173 |
| `replacement_ratio` | 0.0 (no U+FFFD) |
| Avg word length / max | **30.84 / 450** (strong broken-layer signal) |
| Non-ASCII words | 30 / 183 |

Provisional heuristics keyed on replacement characters and coverage **do not detect** this corruption mode. Accepting the page as native creates **plausible-looking false spans**, violating §7 (“routed correctly rather than accepted as usable native text”) and the completion report’s own reference expectation.

---

## 8. SourceToken / SourceSpan contracts

| Check | Result |
|-------|--------|
| Opaque IDs (`tok_` / span ids via `new_opaque_id`) | **PASS** (code review) |
| Span→token integrity / doc+page refs | **PASS** (grouping + models) |
| Coordinates in `[0,1]` | **PASS** (validation + probes) |
| Multi-column non-merge | **PASS** (`test_span_grouping`) |
| Pydantic + generated FE | **PASS** |
| Delete generated → regen ×2 → no drift | **PASS** (`contracts:check OK`) |

---

## 9. Coordinate / highlight findings

| Evidence | Result |
|----------|--------|
| Unit tests (normalize, OOB, rotation 90, zoom scale, columns) | **PASS** |
| Audit math probe (0/90/180/270 × multiple render sizes; crop; 2× zoom linear) | **PASS** |
| UI mapping `normalized × rendered_page_size` in `DocumentViewer` | **PASS** (code review) |
| Full browser visual matrix (DPR, resize, navigate-away, DOCX-derived, private pages) | **Not fully exercised** — headless audit used math + code review only; **no private screenshots committed** |

**Gap:** §9 visual browser evidence is incomplete. Treated as **nonblocking relative to FAIL blockers**, but must be completed before any future audited PASS.

---

## 10. Native usability / OCR routing

| Check | Result |
|-------|--------|
| Thresholds configuration-driven (`AppSettings`) | **PASS** |
| No claim of measured general OCR accuracy | **PASS** (completion + OD-01) |
| UI distinguishes OCR-pending | **PASS** (“awaiting Phase 3 OCR”) |
| No OCR fabricated | **PASS** |
| eCW billing OCR-pending | **FAIL** (see §7) |

### Reference-package aggregate page routes (sampled as processed)

| Alias | Pages | Native | OCR pending | Manual review | Notes |
|-------|-------|--------|-------------|---------------|-------|
| `ecw_medical` | 24 | 24 | 0 | 0 | Strong native — matches expectation |
| `police_like` | 4 | 3 | 1 | 0 | Partial OCR — plausible |
| `insurer_scan` | 1 | 1 | 0 | 0 | Expected mixed/OCR-leaning; scored native |
| `ecw_billing` | 1 | **1** | **0** | 0 | **Expected OCR — FAIL** |
| `long_medical` | 67 | 67 | 0 | 0 | Expected mostly OCR; scored all native under provisional knobs |
| `firm_docx` | 5 | 5 | 0 | 0 | LO convert + native — OK |

Aggregates: native 101, OCR pending 1, manual review 0 (across exercised pages).

Provisional thresholds are **fail-open toward native** for several scan/broken-layer documents. OD-01 allows provisional knobs, but **known-bad billing acceptance is still blocking** under this audit’s §7 criterion.

---

## 11. API isolation findings

Integration coverage in `test_phase02_process.py` (11 passed) exercises:

- Cross-session view/thumbnail denial  
- Access after session delete  
- Access after TTL expiry (`session_expired`)  
- Path-traversal / crafted document id rejection  
- Process events polling  

Contracted errors observed in tests; no filesystem paths in JSON envelopes (log-hygiene unit coverage present).

**PASS** for isolation requirements exercised by automated tests.

---

## 12. Frontend / PDF.js viewer

| Check | Result |
|-------|--------|
| Backend response validation (viewer Zod) | **PASS** (3 viewer schema tests) |
| Worker loading deterministic (`pdf.worker.min.mjs` via `import.meta.url`) | **PASS** |
| Session-scoped canonical URL | **PASS** |
| Thumb/page sync | **PASS** (code review) |
| Zoom remaps highlight via renderSize | **PASS** |
| OCR-pending UI copy | **PASS** |
| DOCX via generated PDF view | **PASS** (architecture + LO evidence) |
| `pdfDoc.destroy` on change | **PASS** (cleanup effect) |
| Render task `cancel()` on rapid page/zoom change | **Gap** — cancelled flag only; **nonblocking** |
| Memory growth under repeated navigation | Not profiled in browser — **nonblocking observation** |

Production build warns on large PDF.js worker chunk (~1.38 MB) — matches completion gap #7.

---

## 13. Reference-package results

Local gitignored package under `docs/example/` **was exercised**. Filenames masked to aliases; content not committed.

| Alias | SHA16 | Norm | Pages | Thumbs | Native / OCR / MR | Duration (s) | Peak MB | Issues |
|-------|-------|------|-------|--------|-------------------|--------------|---------|--------|
| ecw_medical | `9fc3d498462cb55a` | pdf passthrough | 24 | 24 | 24 / 0 / 0 | 19.9 | 27.8 | — |
| police_like | `797da053c3a988c5` | pdf passthrough | 4 | 4 | 3 / 1 / 0 | 1.8 | 8.9 | — |
| insurer_scan | `8212e9d305a0bae1` | pdf passthrough | 1 | 1 | 1 / 0 / 0 | 0.5 | 3.1 | — |
| ecw_billing | `167b9052da1b662e` | pdf passthrough | 1 | 1 | **1 / 0 / 0** | 2.1 | 8.6 | wrong route |
| long_medical | `3350a0702a7cc7aa` | pdf passthrough | 67 | 67 | 67 / 0 / 0 | 84.3 | 22.7 | thresholds fail-open |
| firm_docx | `9e845bb7087269c9` | LibreOffice | 5 | 5 | 5 / 0 / 0 | 4.2 | 17.4 | — |

**Material gap:** no image/TIFF in package (synthetic image/TIFF probes used instead).

---

## 14. Independent regression results

Command: `node scripts/check-all.mjs` on audited tip + lockfiles.

| Gate | Result |
|------|--------|
| Backend ruff format/check | **PASS** |
| Backend mypy strict | **PASS** (66 source files) |
| Backend pytest | **109 passed** |
| JSON Schema generate | **PASS** (26 schemas) |
| Zod generate | **PASS** (26 modules) |
| Contract drift check | **PASS** |
| Drift-proof (tamper) | **PASS** |
| Frontend Prettier | **PASS** |
| Frontend ESLint | **PASS** |
| Frontend `tsc` | **PASS** |
| Frontend vitest | **9 passed** (3 files) |
| Frontend production build | **PASS** (chunk size warning) |

Note: check-all still prints “All Phase 1 checks passed” (cosmetic).

Dual contract regeneration (delete → regen → delete → regen): **no drift**.

---

## Blocking defects

1. **B-01 — PDFium missing process-wide lock**  
   - Requirement: §4 thread-safety  
   - Evidence: `thumbnails.py` has no lock; process can run concurrently across sessions  
   - Impact: native crash / corruption risk under concurrent thumbnail or page-count calls  
   - Owner: Phase 2 hardening (must fix before audited pass)

2. **B-02 — eCW billing accepted as native**  
   - Requirement: §7; FR-EXT-02; matrix/completion expectation for broken billing native layer  
   - Evidence: route=`native`, tokens/spans emitted; avg word length / max length indicate corrupted layer without U+FFFD  
   - Impact: plausible false spans; wrong “usable native” signal  
   - Owner: Phase 2 routing/heuristics fix (or documented calibrated detector) before audited pass; OD-01 remains open for broader calibration

---

## Nonblocking improvements

1. N-01 — Complete browser visual highlight matrix (zoom/DPR/resize/navigate) on synthetic pages; keep private screenshots out of git  
2. N-02 — Timeout kill-tree verification for LibreOffice children on Windows  
3. N-03 — Bound LibreOffice captured stdout/stderr size  
4. N-04 — Tighter app-level image decompression limits beyond Pillow default  
5. N-05 — Cancel in-flight PDF.js render tasks on page/zoom change  
6. N-06 — Code-split / accept PDF.js worker chunk warning  
7. N-07 — Add a synthetic or redacted image/TIFF fixture for CI-adjacent acceptance (not firm PII)  
8. N-08 — Long scanned medical / insurer fail-open-to-native under provisional thresholds (OD-01 / Phase 3) — track explicitly; do not treat as Phase 2 exit satisfaction for “mostly OCR” docs  
9. N-09 — `DocumentPage` contract enrichment (rotation/thumb metadata)  
10. N-10 — Rename check-all success banner beyond “Phase 1”

---

## Exit gate assessment

Matrix exit gate: *selected native fact opens exact source location where native text exists.*

- Implemented via **SourceSpan** selection + highlight overlay (accepted Phase 2 reinterpretation).  
- Works for strong native docs (e.g. `ecw_medical`) per automated geometry + viewer mapping.  
- Undermined for audit pass by **B-02** (false “native usable” spans on known-bad billing) and **B-01** (unsafe concurrent PDFium).

---

## Tag suitability

| Tag | Suitable? |
|-----|-----------|
| `phase-02-audited-pass` at `f6c675f` | **No** |

**Stop.** Do not begin Phase 3. Do not create or move Git tags from this audit.

---

## Appendix — audit artifacts (local only)

Gitignored under `tmp/audit/` (not committed):

- `libreoffice_probe_results.json`  
- `pdfium_probe_results.json`  
- `reference_package_results.json`  
- `ecw_billing_diagnostics.json`  
- `image_norm_results.json`  
- `coordinate_highlight_results.json`  
- Probe scripts: `probe_*.py`  
