# Phase 2 Hardening Independent Re-Audit — B-01 / B-02

**Audit date:** 2026-07-20  
**Auditor:** Fresh independent verification (not the hardening implementer)  
**Method:** Clean tip verification + authoritative doc/contract review + complete PDFium inventory + lock/lifecycle review + deterministic concurrency tests + stress/resource probes + native-usability gate analysis + synthetic fixtures + local reference-package acceptance (aliases/hashes only) + LibreOffice regression + contract dual-regen + full `check-all`  

**Constraints honored:** No production code changes. No Phase 3 work. No PaddleOCR. No Git tag create/move/delete. Audit probes lived only under gitignored `tmp/audit/`.

---

## Final verdict

# PASS

Commit `8930b3259cc076e1c308eefb24cb69f8a79bd08e` is suitable for the immutable tag `phase-02-audited-pass`.

Both blocking findings from the failed Phase 2 audit are closed:

1. **B-01** — process-wide PDFium serialization via sole import boundary [`pdfium_runtime.py`](../../backend/app/services/documents/pdfium_runtime.py).
2. **B-02** — multi-signal native usability gate suppresses unusable eCW billing native text (OCR-pending; zero published tokens/spans).

No blocking regressions. No Phase 3 scope introduced. Do **not** begin Phase 3 in this step; create the tag only via the separate immutable tagging procedure.

---

## Exact audited commit

| Field | Value |
|-------|-------|
| Branch | `phase-02-audit-hardening` |
| **Audited tip** | `8930b3259cc076e1c308eefb24cb69f8a79bd08e` |
| Tip subject | `phase-02: close audit blockers B-01 and B-02` |
| Working tree at audit start | Clean |
| Working tree after probes | Clean of production changes; only intentional new report file |

### Baseline

| Field | Value |
|-------|-------|
| Tag | `phase-01-audited-pass` |
| Peeled commit | `5ab566ff7ad63e51ee8a08f2c7b5ebb6bccec093` |
| Unchanged | **Yes** |
| Ancestor of audited tip | **Yes** |

### Related history

| Commit | Role |
|--------|------|
| `359dab1` | Phase 2 original implementation |
| `f6c675f` | Docs tip audited in FAIL audit |
| `e358d72` | Failed audit evidence — [`phase-02-audit.md`](./phase-02-audit.md) preserved |
| `8930b32` | Hardening under audit — [`phase-02-hardening.md`](./phase-02-hardening.md) |

---

## 1. Git history and scope

| Check | Result |
|-------|--------|
| `HEAD` == `8930b32…` | **PASS** |
| Working tree clean before audit | **PASS** |
| `phase-01-audited-pass` unchanged | **PASS** |
| Failed audit report committed | **PASS** (`e358d72`) |
| Hardening diff limited to B-01/B-02 + tests + contracts/config + reports | **PASS** |
| No PaddleOCR / semantic extraction / classification / facts / billing interpretation / LLM / drafting / export services introduced | **PASS** (contract stubs / settings flags only; no Phase 3 engines) |
| No confidential PDFs/DOCX/patient text/OCR weights/credentials/local paths committed | **PASS** (reference binaries remain gitignored under `docs/example/`) |

### Diff `e358d72..8930b32` (15 files)

- `backend/app/services/documents/pdfium_runtime.py` (new)
- `backend/app/services/documents/thumbnails.py`
- `backend/app/services/extraction/routing.py`
- `backend/app/models/app_settings.py`
- Tests: `test_pdfium_import_boundary.py`, `test_pdfium_concurrency.py`, `test_native_usability_gate.py`, integration concurrent process
- Contracts/docs: `app-settings.md`, `document-page.md`, `03-ocr-thresholds.md`, generated AppSettings schema/Zod
- Reports: `phase-02-hardening.md`, completion touch-up

No unrelated feature work in the hardening commit.

---

## 2. Complete PDFium import / call inventory

| Location | Finding |
|----------|---------|
| `backend/app/services/documents/pdfium_runtime.py` | **Only** production `import pypdfium2` |
| `backend/app/services/documents/thumbnails.py` | Calls `pdfium_runtime` only (no direct pypdfium2) |
| `backend/app/**` other | **None** (`pypdfium2.raw` / `pypdfium2_raw` / importlib aliases absent) |
| `spikes/ocr/run_benchmark.py` | Spike-only import (allowed; not application path) |
| Tests | May import runtime / use pypdf fixtures; architectural AST test enforces app boundary |

**Architectural enforcement:** `tests/unit/test_pdfium_import_boundary.py` AST-scans `backend/app` and fails if a second production importer appears — **PASS** (ran independently).

**Public runtime ops under lock:** `count_pages`, `render_all_pages`, `render_page`. Thumbnail resize/PNG save runs **outside** the lock after detached PIL copies. Native `PdfDocument` / page / bitmap handles never escape the critical section.

---

## 3. Process-wide lock and lifecycle analysis

| Requirement | Finding |
|-------------|---------|
| `RLock` at module/process scope | **PASS** — `_PDFIUM_LOCK = threading.RLock()` |
| Shared across service instances | **PASS** — `get_pdfium_lock()` identity test |
| Threadpool / concurrent requests cannot bypass | **PASS** — all PDFium ops enter `_critical_section` |
| Nested helpers do not deadlock | **PASS** — `RLock`; no nested public ops that re-enter while holding caller locks incorrectly |
| Critical section covers full native lifetime | **PASS** — open/render/close inside `with _PDFIUM_LOCK` |
| Native objects closed before release | **PASS** — `try/finally` page + pdf close; PIL `.copy()` then close |
| Exceptions release lock | **PASS** — context manager + fault-injection test |
| Cancel simulation does not permanently hold lock | **PASS** — `InterruptedError` fault then subsequent `count_pages` OK |
| Failed ops do not block later work | **PASS** |
| Non-PDFium work outside lock | **PASS** — thumbnail resize/save after render returns |
| GIL not treated as substitute | **PASS** — explicit process-wide lock |

Inflight observability uses a separate `_inflight_lock` so the max-inflight counter cannot hide overlap.

---

## 4. Concurrency test evidence

Independent run (`pytest` from hardening tip):

| Test | Result |
|------|--------|
| `test_only_pdfium_runtime_imports_pypdfium2` | PASS |
| Concurrent thumbnails (2 docs) — barrier, max inflight == 1 | PASS |
| Count overlaps render — max inflight == 1 | PASS |
| Four-way contention — max inflight == 1 | PASS |
| Exception releases mutex; subsequent work OK | PASS |
| Cancel simulation does not permanently lock | PASS |
| Separate callers share same lock object | PASS |
| Two sessions concurrent `POST /process` — max inflight == 1 | PASS |

**8 passed** for PDFium-focused selection. Primary correctness mechanism: `threading.Barrier` + enter/exit/fault hooks — **not** sleep-based.

### Stress probe (synthetic blank PDFs only)

`tmp/audit/probe_pdfium_stress.py`: 8 threads × 10 ops = **80** mixed count/thumbnail operations across 6 documents.

| Metric | Value |
|--------|-------|
| Errors | `[]` |
| Max inflight | **1** |
| Elapsed | 0.631s |
| Pass | **true** |

Reference concurrent thumbs (`ecw_billing` + `police_like`): max inflight **1**, both thumbnails written.

### Resource / lifetime probe

`tmp/audit/probe_pdfium_resource.py`: 40 sequential count+thumbnail cycles.

| Metric | Value |
|--------|-------|
| Tracemalloc samples | ~725–792 KB current; peak ~3.6 MB (stable, no unbounded climb) |
| Open-handle sampling | `psutil` unavailable in env (`null`); no crash/leak symptom in repeated cycles |
| Pass | **true** |

---

## 5. Native-usability gate analysis (B-02)

Implementation: [`routing.py`](../../backend/app/services/extraction/routing.py) + settings in [`AppSettings`](../../backend/app/models/app_settings.py).

| Property | Result |
|----------|--------|
| Page-level | **PASS** |
| Deterministic | **PASS** |
| Configuration-driven (provisional SoT) | **PASS** — matches [`03-ocr-thresholds.md`](../modules/03-ocr-thresholds.md) / [`app-settings.md`](../contracts/entities/app-settings.md) `0.1-provisional` |
| Independent of filename/provider/identity | **PASS** |
| Multi-signal (not max-length alone) | **PASS** |

### Signals reviewed

Character/word counts; mean/median/max token length; long-token ratio (band 40); printable / control / replacement ratios; CID markers; private-use glyphs; repeated-glyph anomalies; zero-width/overlap; oversized boxes; reading-order score; blank / image-coverage scan lean.

**Pathological composite (documented):**

1. `long_token_ratio > max` AND (`mean > max_mean` OR `median > max_median`), or  
2. `mean > max_mean` AND `median > max_median`

### Configured defaults (match SoT)

| Setting | Default |
|---------|---------|
| `native_long_token_band` | 40 |
| `native_max_long_token_ratio` | 0.20 |
| `native_max_mean_token_length` | 24 |
| `native_max_median_token_length` | 18 |
| `native_min_printable_ratio` | 0.90 |
| `native_max_control_char_ratio` | 0.02 |
| `native_max_oversized_box_ratio` | 0.20 |

### Hidden heuristic constants (nonblocking)

Fixed ratios not exposed as `AppSettings` knobs: per-token “huge box” fraction `0.25` of page area; CID/private-use ratio `0.05`; repeated-glyph ratio `0.15`; repeated-glyph regex `(.)\1{8,}`. These are stable heuristics in code; material routing effect is covered by tests/probes. Prefer promoting to documented settings in a later calibration pass (OD-01) — **not** a B-02 reopen.

---

## 6. B-02 behavior and artifact suppression

For OCR-routed pages ([`native.py`](../../backend/app/services/extraction/native.py)):

| Check | Result |
|-------|--------|
| Route `ocr` / `ocr_status=pending` | **PASS** |
| Flags include `pathological_tokenization` / `broken_text_layer` / `awaiting_ocr` as applicable | **PASS** |
| Not marked blank when text exists | **PASS** |
| Zero SourceTokens / SourceSpans published | **PASS** |
| Reprocess idempotent (still zero) | **PASS** (billing twice) |
| PaddleOCR not invoked | **PASS** (AST: no paddle imports under `backend/app`) |
| Canonical PDF + thumbnails available | **PASS** |

API leak check (billing): pages / tokens / spans endpoints return empty lists; process events carry route status only (no token text payloads observed in page.processed). Frontend shows “awaiting Phase 3 OCR” and “Native spans are unavailable” for `route === "ocr"` ([`DocumentViewer.tsx`](../../frontend/src/components/DocumentViewer.tsx)).

---

## 7. Synthetic fixture results

`tests/unit/test_native_usability_gate.py` — **12 passed**.

| Fixture class | Expected | Observed |
|---------------|----------|----------|
| Normal prose | native | PASS |
| Dense table | native | PASS |
| Single long URL | native | PASS |
| Long identifier | native | PASS |
| Mixed long + normal | native | PASS |
| Pathological missing whitespace | OCR | PASS |
| Extremely long malformed tokens | OCR | PASS |
| CID-like | OCR | PASS |
| Blank | manual_review | PASS |
| Image-only / sparse + high image coverage | OCR | PASS |
| No PaddleOCR in extraction package | — | PASS |

Supplemental auditor probes (not in unit file, but exercised):

| Signal | Route |
|--------|-------|
| Control characters | OCR |
| Replacement characters | OCR |
| Repeated glyph corruption | OCR |
| Oversized geometry | OCR |

**Coverage note (nonblocking):** dedicated unit tests for control/replacement/geometry are thinner than pathological/CID/prose cases; supplemental probes confirm routing.

---

## 8. Local reference-package acceptance (aliases / hashes only)

Location: gitignored `docs/example/`. No filenames, patient text, or screenshots recorded.

| Alias | SHA16 | Pages | Native / OCR / MR | Published tokens / spans | Notes |
|-------|-------|-------|-------------------|--------------------------|-------|
| `ecw_billing` | `167b9052da1b662e` | 1 | 0 / **1** / 0 | **0 / 0** | B-02 closed |
| `ecw_medical` | `9fc3d498462cb55a` | 24 | **24** / 0 / 0 | 7679 / 1003 | Independent **24/24** |
| `police_like` | `797da053c3a988c5` | 4 | 3 / 1 / 0 | (API exercised) | Matches prior mix |
| `insurer_scan` | `8212e9d305a0bae1` | 1 | 1 / 0 / 0 | (API exercised) | Usable native layer on sample |
| `long_medical_scan` | (local large PDF) | 67 | 67 / 0 / 0 | 17565 / — | Extractable text layer under provisional thresholds |

### eCW billing (B-02 closure)

| Check | Result |
|-------|--------|
| Page count | 1 |
| Route | **OCR pending** |
| Published usable tokens/spans | **0 / 0** |
| Safe pre-suppression diagnostics | mean≈30.84; median=13; max_len=450; long_token_ratio≈0.2295; `pathological_tokenization=true` |
| View PDF + thumbnail | OK |
| Reprocess idempotent zeros | OK |
| Cross-session denied | OK |
| PaddleOCR | Not called |

### eCW medical

| Check | Result |
|-------|--------|
| 24/24 native | **PASS** (independent) |
| Tokens/spans available | 7679 / 1003 |
| Page-1 span geometry in unit square, non-degenerate | **PASS** (16 spans; 4-point polygon) |
| Post-delete access | 404 |
| Text quality degraded by over-aggressive thresholds | **No** — all pages remain native |

### Other

Police/insurer aggregates match hardening report shape. Concurrent reference thumbnails serialize (max inflight 1). `long_medical_scan` scoring fully native is a **provisional-threshold / OD-01 calibration observation** (document has extractable native words); it is **not** the broken-billing false-native defect class and does **not** reopen B-02.

---

## 9. API / frontend regression

| Check | Result |
|-------|--------|
| OCR-pending UI status string | **PASS** |
| Rejected pages: no native span list to select | **PASS** (empty + explicit message) |
| Good native: spans + highlight mapping | **PASS** (unit coords + medical span geometry) |
| Thumbnails / zoom / nav controls present | **PASS** (code + thumb API) |
| Backend responses validate against generated contracts | **PASS** (TestClient model_validate paths) |
| Cross-session / deleted session blocked | **PASS** |
| No filesystem path disclosure in view responses | **PASS** |

---

## 10. LibreOffice and Phase 2 load-bearing regression

### Real LibreOffice

| Probe | Result |
|-------|--------|
| Path resolved | Yes (`ServerSettings.libreoffice_path`) |
| Synthetic DOCX → PDF | OK (1.254s); original bytes unchanged |
| Two concurrent conversions | Both OK (2.25s wall; process-wide conversion lock) |

### Automated Phase 2 paths

| Suite | Result |
|-------|--------|
| `test_phase02_process.py` + coordinates + native extraction | **20 passed** |
| Full backend pytest via `check-all` | **129 passed** |

Normalization, thumbnails, page metadata, session isolation, and contract regeneration remain green. B-01/B-02 fixes did not regress these paths.

---

## 11. Contract and configuration

| Check | Result |
|-------|--------|
| New settings + quality flag vocabulary in `docs/contracts/` | **PASS** |
| Pydantic ↔ JSON Schema ↔ Zod agree | **PASS** |
| Generate + drift check (including dual pass via `check-contracts`) | **PASS** — no drift |
| No implementation-only enum bypassing contracts | **PASS** (`PageRoute` / flags as documented additive strings) |
| Frontend recognizes OCR-pending | **PASS** (`ocr_status === "pending"`) |

---

## 12. Clean verification (`node scripts/check-all.mjs`)

Exact umbrella command: `node scripts/check-all.mjs` (2026-07-20).

| Gate | Result |
|------|--------|
| `ruff format --check` / `ruff check` | PASS |
| `mypy` strict (67 files) | PASS |
| `pytest -q` | **129 passed** |
| JSON Schema generate | PASS |
| Zod generate | PASS |
| `check-contracts` | **no drift** |
| Drift-proof | PASS |
| Frontend prettier / eslint / tsc | PASS |
| `vitest` | **9 passed** |
| Production build | PASS (PDF.js chunk size warning unchanged, nonblocking) |

Baselines met: backend ≥129, frontend ≥9, build success, no contract drift. No count reduction.

---

## 13. Repository safety

| Artifact class | Committed? |
|----------------|------------|
| Firm/case PDFs under `docs/example/` | No (gitignored; local only) |
| Extracted patient text / private derivatives | No |
| Screenshots of private evidence | No |
| `.env` / credentials | No |
| `.venv` / `node_modules` / session dirs / OCR weights | No |
| Absolute local machine paths in committed sources | No |

Note: `docs/prototype_documentation.docx` remains a committed product-doc artifact (pre-existing; not case evidence).

Audit probe outputs remain under gitignored `tmp/audit/`.

---

## 14. Blocking defects

**None.**

B-01 and B-02 from [`phase-02-audit.md`](./phase-02-audit.md) are closed with automated and local reference evidence.

---

## 15. Nonblocking observations

1. **OD-01 provisional thresholds** remain uncalibrated for general OCR accuracy; fail-open to OCR is intentional for pathological cases.
2. Some scan-like packages with usable text layers still route native (`insurer_scan`; `long_medical_scan` 67/67) — calibration topic, not billing false-native.
3. Hidden CID/repeated/oversized heuristic constants should eventually become documented settings.
4. Mid-request PDFium cancel is simulated via exception hooks (Phase 2 has no async cancel API).
5. `psutil` not installed — open-file-handle trend not numerically sampled; tracemalloc showed stable memory across repeated renders.
6. Large PDF.js worker chunk warning in production build (pre-existing).
7. Synthetic unit suite could add explicit control/replacement/geometry cases (signals verified by supplemental probes).

---

## 16. Final verdict (restated)

# PASS

Commit `8930b3259cc076e1c308eefb24cb69f8a79bd08e` is suitable for the immutable tag `phase-02-audited-pass`.

Stop. Do not begin Phase 3. Do not create the tag in this audit step.
