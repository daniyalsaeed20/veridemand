# Phase 3 Independent Audit — OCR and Page Quality

**Audit date:** 2026-07-20  
**Auditor:** Fresh independent verification (not the Phase 3 implementer’s PASS WITH GAPS claim)  
**Method:** Clean tip verification + authoritative doc/contract review + paddle import inventory + adapter lifecycle/serialization probes + PDFium/OCR lock-order review + delete-during-process race probe + reference-package acceptance (aliases/hashes only) + police under-detection investigation + Jackman long-medical correction + OCR quality/coordinate unit evidence + frontend OCR-state review + perf/RSS measurement + contract dual-regen + full `check-all`

**Constraints honored:** No production code changes. No Phase 4 work. No Git tag create/move/delete. Audit probes lived only under gitignored `tmp/audit/`. Shared OCR model cache was not deleted.

---

## Final verdict

# FAIL

Commit `982651a7237ae3b1b2ec76a7d41269adf42c24a4` is **not** suitable for the immutable tag `phase-03-audited-pass`.

Phase 3 delivers a large share of the intended OCR path (sole PaddleOCR adapter, CPU pin, single-worker lock, PDFium released before OCR, native-first routing, OCR tokens/spans, multi-signal quality flags, automated gates). Three **blocking** defects prevent an audited pass:

1. **B-01** — OCR engine initialization failure permanently poisons the process-wide adapter until process restart (`reset_adapter_state` is test-only).
2. **B-02** — Session `DELETE` during active process/normalization intermittently returns `500 session_cleanup_failed` (7/20 race runs) while the client expects a clean delete.
3. **B-03** — Police OCR-routed page 4 is marked `ocr_usable` with only **6** tokens despite substantial rendered ink (`dark_pixel_fraction ≈ 0.335`) — unexplained under-detection presented as success.

Do **not** create `phase-03-audited-pass`. Do **not** begin Phase 4 until these blockers are fixed and re-audited.

---

## Exact audited commit

| Field | Value |
|-------|-------|
| Branch | `phase-03-ocr-page-quality` |
| **Audited tip** | `982651a7237ae3b1b2ec76a7d41269adf42c24a4` |
| Tip subject | `phase-03: implement OCR page quality with PaddleOCR adapter` |
| Working tree at audit start | Clean |
| Working tree after probes | Clean of production changes; only intentional new report file + gitignored `tmp/audit/` |

### Baseline

| Field | Value |
|-------|-------|
| Tag | `phase-02-audited-pass` |
| Peeled commit | `8930b3259cc076e1c308eefb24cb69f8a79bd08e` |
| Unchanged | **Yes** |
| Ancestor of audited tip | **Yes** |

### Related history (`phase-02-audited-pass..982651a`)

| Commit | Role |
|--------|------|
| `bf25cda` | Docs: Phase 2 hardening re-audit PASS |
| `982651a` | Phase 3 OCR implementation under audit |

### Prior tags (unchanged)

`phase-00-pass`, `phase-01-pass`, `phase-01-audited-pass`, `phase-02-audited-pass`

---

## 1. Git, baseline and scope

| Check | Result |
|-------|--------|
| `HEAD` == `982651a…` | **PASS** |
| Working tree clean before audit | **PASS** |
| Descends from `phase-02-audited-pass` | **PASS** |
| Prior audited tags unchanged | **PASS** |
| No Phase 4 classification / sequence services | **PASS** |
| No structured fact extraction / billing interpretation / chronology / contradiction / LLM / drafting / export runtime | **PASS** (contract stubs remain; no Phase 4+ services) |
| No real case docs / OCR weights / credentials committed | **PASS** (reference binaries remain gitignored under `docs/example/`; weights under `%LOCALAPPDATA%/VeriDemand/paddleocr`) |

### Diff scope (`phase-02-audited-pass..982651a`)

~40 files / ~3.8k insertions: OCR adapter (`adapter.py`, `model_paths.py`, `types.py`), extraction (`ocr_page.py`, `ocr_quality.py`, `preprocess.py`, coordinates/spans/routing touch-ups), process/session/API/health, AppSettings/enums/contracts, frontend OCR states, tests, `phase-03-completion.md`, dependency inventory / `uv.lock`, local-setup.

### Implementer claim

[`phase-03-completion.md`](./phase-03-completion.md) claimed **PASS WITH GAPS**. Treat as a claim only.

---

## 2. Dependency and model-cache result

| Item | Result |
|------|--------|
| Installed `paddleocr` | **2.7.3** |
| Installed `paddlepaddle` | **2.6.2** |
| PaddleOCR 3.x present | **No** |
| `pyproject.toml` pins | `paddleocr==2.7.3`, `paddlepaddle==2.6.2` |
| `uv.lock` | Matches pins; `uv sync --extra dev` → **no lockfile drift** |
| Python | **3.12.8** (backend `.venv`) |
| OS | **Windows 10 (10.0.19045)** |
| CPU default | **Yes** (`use_gpu=False`) |
| Model names | English det / rec / cls under cache `det/`, `rec/`, `cls/` (`inference.pdmodel` + `inference.pdiparams`) |
| Cache location | `%LOCALAPPDATA%/VeriDemand/paddleocr` (override `VERIDEMAND_OCR_MODEL_DIR`) — **outside repo** |
| Health before model init | **PASS** — `ocr_enabled` uses `importlib.find_spec` only |
| Warm init from populated cache | **PASS** — ~5.1 s engine load without re-download |
| Offline warm-start | **PASS** (cache already populated; warm `ensure_engine` succeeded) |
| Missing/corrupt models | Clear `OcrUnavailableError` path exists; sticky failure behavior tracked under **B-01** |
| Model paths to FE / unsafe logs | **PASS** — health/events do not expose absolute cache paths |

Inventory recorded in [`DEPENDENCY_INVENTORY.md`](../../DEPENDENCY_INVENTORY.md). OD-15 (CPU) and OD-16 (pin A) resolved.

---

## 3. OCR adapter / import inventory

| Location | Role |
|----------|------|
| `backend/app/services/ocr/adapter.py` | **Sole** production `from paddleocr import PaddleOCR` / `engine.ocr` |
| `spikes/ocr/run_benchmark.py` | Spike only (non-production) |
| Extraction / API / UI / process | Call `recognize_image` — **no** direct paddle imports |

Architectural test: [`backend/tests/unit/test_ocr_import_boundary.py`](../../backend/tests/unit/test_ocr_import_boundary.py) AST-walks `backend/app` and allows only `services.ocr.adapter`.

Fake engines (`set_fake_engine`) are test instrumentation; production process path uses the real adapter unless tests inject fakes. Local acceptance / audit probes that need real OCR do not leave fakes installed.

**Result:** Adapter boundary **PASS**.

---

## 4. Initialization result

| Property | Result |
|----------|--------|
| Lazy load | **PASS** — first `recognize_image` |
| One instance per process | **PASS** — module singleton + `_INIT_LOCK` |
| Concurrent first recognize | **PASS** — `max_inflight == 1` under barrier (fake engine) |
| Failed recognize releases lock | **PASS** (unit + finally path) |
| Cancel releases / clears for later work | Partial — cancel Event works; see N-01 for process-wide scope |
| Init failure retry | **FAIL — B-01** |

**B-01 evidence:** After `_init_attempted` + `_init_error` are set, subsequent `ensure_engine()` raises without retry. Only `reset_adapter_state()` (test helper) clears poison. Probe: `tmp/audit/adapter_lifecycle.json` → `sticky_poison_confirmed: true`.

Cold vs warm (this machine, populated cache):

| Metric | Observed |
|--------|----------|
| Warm engine init | ~4.8–5.1 s |
| Blank-page recognize after warm | ~0.16–0.57 s |
| Reported cold (~37 s) | Consistent with first-time **download + init + dense page**; not re-measured as cold download (cache preserved) |

---

## 5. Serialization and lock-order result

### Single-worker OCR

| Check | Result |
|-------|--------|
| Process-wide `_OCR_WORKER_LOCK` | **PASS** |
| `AppSettings.ocr_workers` must be 1 | **PASS** |
| Cross-session max inflight ≤ 1 | **PASS** (`test_two_sessions_serialize_ocr_worker` + unit barrier) |
| Instrument: `maximum simultaneous OCR inference == 1` | **PASS** (`get_max_inflight()`) |

### Lock order

Documented and code-reviewed path:

```text
session/generation check
  → PDFium lock (render only) → release detached PIL
  → preprocess (no PDFium / no session lock)
  → OCR worker lock → release
  → re-check generation → commit or discard
```

| Check | Result |
|-------|--------|
| PDFium released before OCR | **PASS** |
| SessionService lock not held during render/OCR | **PASS** (code review of `process/service.py`) |
| No reverse OCR→PDFium acquisition in OCR path | **PASS** |
| Generation gate blocks late commit | **PASS** (commit checks `record.generation`) |
| Delete mid-process discards work | **Partial** — generation cancel works; DELETE HTTP status flaky (**B-02**) |

**N-01 — Process-wide cancel Event:** `SessionService.delete` / expire calls `request_cancel()` which sets a **process-global** Event. Deleting session B can cancel session A’s in-flight OCR. `clear_cancel()` at process start recovers new jobs. Prototype risk; not elevated to B because generation gates still prevent cross-session commits.

---

## 6. Routing result

Independent reference re-check (safe aliases / SHA16):

| Alias | SHA16 | Pages | Native | OCR | Notes |
|-------|-------|------:|-------:|----:|-------|
| ecw_medical | `9fc3d498462cb55a` | 24 | 24 | 0 | Native preserved; CID 0 on sampled pages |
| ecw_billing | `167b9052da1b662e` | 1 | 0 | 1 | OCR **136** tokens; warning (**§11**) |
| police | `797da053c3a988c5` | 4 | 3 | 1 | Pages 1–3 strong native; page 4 OCR (**B-03**) |
| insurer | `8212e9d305a0bae1` | 1 | 1 | 0 | Native text layer usable |
| long_medical (Jackman) | `3350a0702a7cc7aa` | **67** | **67** | 0 | See alias note below |

Routing is content/diagnostics-driven (not filename). `OCR_FORCE_FOR_TESTS` is settings-gated for tests.

### Long-medical completeness / alias defect

- True Jackman stack: **67 pages**, all native-first, CID ratio 0 on sampled pages (1 / mid / last), plausible token densities.
- Acceptance script patterns for `long_medical` (`*MEDICAL*RECORDS*` before `*JACKMAN*`) **resolve to eCW medical first** — completion table’s “long_medical 6 pages” is a **documented subset of the wrong file** (max_pages=6 on eCW medical). Independent correction recorded under **N-02**.

Native-first pages (police 1–3, insurer, eCW medical, Jackman samples): usable native beyond “text exists” — non-zero coverage, high reading-order scores, no CID corruption on samples.

---

## 7. OCR engine-output and geometry result

| Check | Result |
|-------|--------|
| Parse rejects `None` / malformed nesting / non-list | **PASS** (`_parse_paddle_result` warnings) |
| Confidence clamped to `[0,1]` | **PASS** |
| Degenerate / large-OOB polygons rejected | **PASS** (`image_polygon_to_normalized`) |
| Empty text skipped | **PASS** (`detections_to_tokens`) |
| Method provenance `ocr` | **PASS** |
| Stable opaque token IDs | **PASS** |
| Unit coverage | `test_ocr_coordinates_quality.py`, `test_ocr_adapter.py` |

**N-03 — Deskew coordinate transform:** Retry preprocess may deskew via OpenCV without an explicit inverse map back to canonical page space. First-pass uses identity (common path). Deskewed retry polygons can mis-align overlays if deskew wins the score — gap for full rotation/deskew matrix (§9).

Rotations 0/90/180/270 and CropBox matrices: code paths exist for native pdfplumber; OCR path assumes PDFium bitmap already matches viewer (`page_rotation=0` after render). Synthetic unit coverage for basic normalize; full browser DPI/zoom matrix not re-shot in this audit (existing PDF.js overlay math unchanged from Phase 2).

---

## 8. SourceSpan construction

| Check | Result |
|-------|--------|
| Spans reference OCR token IDs via `group_tokens_into_spans` | **PASS** (shared Phase 2 grouper + OCR method) |
| Native vs OCR distinguishable | **PASS** (`method`) |
| Reprocess replaces rather than unbounded growth | **PASS** (`test_reprocess_idempotent_ocr_artifacts`) |
| Confidence aggregation | Page quality uses mean + multi-signal flags — does not invent facts |

---

## 9. Quality / warning result (`ecw_billing`)

Reproduced independently:

| Field | Value |
|-------|-------|
| Outcome | `ocr_usable_with_warning` |
| Tokens | **136** |
| Mean recognition confidence | **≈ 0.984** (not the warning driver) |
| Triggered flag | `duplicate_page` |
| Warning | `duplicate_text_detections` (`duplicate_ratio` heuristic) |
| Bands | top 63 / mid 64 / bot 9 — table regions represented |
| User-visible | `quality_flags` include warning; UI shows “recognition warning (not legal verification)” when `low_confidence` — **note:** billing warning uses `duplicate_page`, not `low_confidence`, so Retry OCR button may **not** appear for this specific flag (**N-04**) |
| Downstream | Tokens/spans published; not promoted to verified facts |
| Reproducible | **Yes** |

Mean confidence is **not** the sole decision signal — overlap/duplicate/printable/critical-looking heuristics also apply. Empty OCR → `blank` + Issue. `OcrPageOutcome.FAILED` is defined but **never returned** by `assess_ocr_tokens` (**N-05**).

---

## 10. Reference-package transcription checks

Safe aggregates only (no patient text recorded).

| Page | Check | Aggregate outcome |
|------|-------|-------------------|
| ecw_billing OCR | Token count / bands / warning | 136 tokens; multi-band coverage; warning justified by duplicate detections |
| police p4 OCR | Token count vs ink | **6 tokens**, coverage ≈ 0.01, dark fraction ≈ 0.335 → **under-detection suspect (B-03)** |
| Native pages | CID / order / density | Usable on sampled native-first pages |

Hallucination vs missing lines on police p4: sparse OCR output on a dense-ink page is consistent with **missing** content, not fabrication of long prose. Still unsafe to treat as complete extraction while `ocr_usable`.

---

## 11. Police six-token investigation

| Field | Value |
|-------|-------|
| Page | 4 of 4 |
| Native before OCR | `char_count=64`, `text_coverage≈0.014` → route **ocr** (correct fail-open) |
| OCR tokens | **6** / 4 spans |
| Outcome | `ocr_usable` (mean conf ≈ 0.93) |
| Dark pixel fraction @ 200 DPI | **≈ 0.335** |
| Under-detection suspect | **Yes** |

**Verdict:** Not a genuinely blank/sparse page. Material unexplained under-detection while marked usable → **B-03**.

---

## 12. Native regression

| Check | Result |
|-------|--------|
| ecw_medical 24/24 native | **PASS** |
| PDFium max inflight 1 | Preserved (Phase 2 runtime; not regressed by OCR lock separation) |
| Native APIs / highlights | Present; OCR method badge additive |
| DOCX/thumbnails | Unchanged dependency path; `check-all` green |

---

## 13. Preprocessing and retry

| Check | Result |
|-------|--------|
| Max one preprocess+OCR retry | **PASS** |
| Triggered by low mean conf / blank / low-conf outcome | **PASS** |
| Better-pass selection deterministic | **PASS** (`score_pass_for_retry_choice`) |
| Not applied on first pass by default | **PASS** (identity) |
| No LLM/vision primary fallback | **PASS** |
| Temp images closed | **PASS** (`prepared.image.close()`) |
| Deskew inverse transform | **N-03** |

---

## 14. Artifact replacement and idempotency

| Check | Result |
|-------|--------|
| Reprocess replaces page tokens | **PASS** (integration) |
| Generation mismatch discards commit | **PASS** (code) |
| Deleted session access | 404 after delete (even when DELETE returned 500 — registry popped) |

---

## 15. Progress and frontend states

| State | Backend / FE |
|-------|----------------|
| Process + OCR events | `document.ocr.*` counted in `App.tsx` after poll to `process.completed` |
| OCR pending / done / failed | Shown in `DocumentViewer` meta + thumbs |
| Native vs OCR badge | **PASS** |
| Confidence as legal verification | Explicitly disclaimed in UI copy | 
| Live poll while viewer open + pending | **Missing — N-06** (pages/spans loaded once; may stale until remount/retry) |
| Progress PII | Events reviewed as structured codes; OCR text not in normal event payloads |

---

## 16. Lifecycle, security and privacy

| Check | Result |
|-------|--------|
| Cross-session token access | **PASS** → 404 (`test_cross_session_token_access_denied`) |
| Contracted errors | Domain error codes used |
| Model/cache paths not in FE | **PASS** |
| Weights outside git | **PASS** |
| **DELETE during process** | **FAIL — B-02** (7/20 → 500 `session_cleanup_failed`; workspace delete races writer) |

---

## 17. Performance and memory

Independent measurements (warm cache, developer machine):

| Metric | Observed | vs completion claim |
|--------|----------|---------------------|
| Warm engine init | ~4.8–5.1 s | Cold ~37 s included first download — not re-run cold |
| Billing page (warm) | ~6.8 s total; OCR ~6.8 s; render ~54 ms | Completion warm police ~1.6 s OCR — page density differs |
| Second billing OCR | ~5.8 s | Stable order of magnitude |
| Native eCW medical 24p | Prior acceptance ~3.7 s | Not re-timed this run; routing unchanged |
| Peak RSS (process sample) | **≈ 828 MB** after billing OCR | Spike band ~700–1015 MB; **now measured** |
| Memory after repeat | RSS stabilized ~818–828 MB across second page | Nonblocking |

**Peak RSS gap in completion script:** previously empty; auditor measured with `psutil` → **nonblocking** relative to exit gate once documented (matrix asks for baselines; OD-01 provisional). Not a blocker by itself.

---

## 18. Duplicate-page heuristic

| Check | Result |
|-------|--------|
| Does not auto-delete evidence | **PASS** — warning flag only |
| Exact hash vs visual similarity | Heuristic text-duplicate ratio — provisional (**N-07**) |
| Can over-flag dense tables (billing) | Observed — appropriate as warning, not silent drop |

---

## 19. Handwriting boundary

Flag/Issue path only; no universal handwriting OCR claim; no LLM vision fallback added. **PASS** as expected prototype behavior.

---

## 20. Contracts and deterministic generation

| Check | Result |
|-------|--------|
| `OcrStatus` closed vocab | `not_needed` \| `pending` \| `done` \| `failed` |
| Quality flags documented | Including `duplicate_detections` / `duplicate_page` |
| Dual contract regen + drift | **PASS** (`check-all` / `contracts:check OK — no drift`) |
| Frontend Zod for AppSettings / DocumentPage | Regenerated; viewer tests cover OCR fields |

---

## 21. Clean regression verification

| Gate | Result |
|------|--------|
| `uv sync` lock drift | **none** |
| Backend format / lint / mypy | **PASS** |
| Backend pytest | **147 passed** |
| Frontend format / lint / typecheck | **PASS** |
| Frontend vitest | **9 passed** |
| Frontend production build | **PASS** |
| Contract gen ×2 + drift | **PASS** |
| `node scripts/check-all.mjs` | **PASS** (“All Phase 1 checks passed.” umbrella) |

No test-count reduction vs completion claim.

---

## 22. Repository-safety result

| Check | Result |
|-------|--------|
| No `.pdparams` / model weights in git | **PASS** |
| No committed reference PDFs | **PASS** (gitignored local package) |
| No credentials / `.env` in tip | **PASS** |
| Audit probes under `tmp/audit/` | gitignored |

---

## Blocking defects

### B-01 — Sticky OCR initialization failure

| Field | Content |
|-------|---------|
| Requirement | Audit §4 / FR-EXT-05 lifecycle — transient init failure must not permanently poison the worker; later retry should be possible where supported |
| Evidence | `ensure_engine()` sets `_init_attempted` + `_init_error` and re-raises forever; only test `reset_adapter_state()` clears. Probe `tmp/audit/adapter_lifecycle.json` |
| Impact | One transient model/IO failure disables OCR for the whole process until restart |
| Owner | Phase 3 hardening |

### B-02 — Session DELETE race during active process

| Field | Content |
|-------|---------|
| Requirement | Audit §6 lifecycle — session deletion during render/OCR must be safe and deterministic |
| Evidence | 20× delete-during-process probe: **13× 204**, **7× 500** `session_cleanup_failed` (`tmp/audit/delete_during_ocr_race.json`). Writer continues after workspace delete. Single-shot pytest can pass luckily |
| Impact | Unreliable cleanup API; client may see hard failure; logging races on closed streams |
| Owner | Phase 3 hardening (session delete vs process writer coordination) |

### B-03 — Police OCR page under-detection marked usable

| Field | Content |
|-------|---------|
| Requirement | Audit §12 — unexplained under-detection is a material gap; pages must be extracted **or** explicitly flagged |
| Evidence | Page 4: 6 OCR tokens, coverage ≈ 0.01, dark_pixel_fraction ≈ 0.335, outcome `ocr_usable` (`tmp/audit/long_medical_police_fix.json`) |
| Impact | Incomplete OCR presented as successful usable evidence — silent incompleteness risk for later parsers |
| Owner | Phase 3 hardening (coverage/under-detection gate → warning or review) |

---

## Nonblocking gaps

| ID | Gap |
|----|-----|
| N-01 | Process-wide OCR cancel Event shared across sessions |
| N-02 | `phase03_reference_acceptance.py` `long_medical` alias collides with eCW medical; Jackman is 67 native pages |
| N-03 | Deskew retry lacks explicit inverse transform to canonical page space |
| N-04 | UI Retry OCR keyed on `failed` / `low_confidence` — misses `duplicate_page`-only warnings |
| N-05 | `OcrPageOutcome.FAILED` never emitted by `assess_ocr_tokens` |
| N-06 | DocumentViewer does not live-poll while `ocr_status=pending` |
| N-07 | Duplicate-page heuristic provisional (OD-01 / FR-EXT-07) |
| N-08 | Health `ocr_enabled` means packages importable, not models warm |
| N-09 | Module index still lists Module 03 as `design`; App lede still says “Phase 2” |
| N-10 | Handwriting / peak-RSS previously incomplete in completion — peak RSS now auditor-measured (~828 MB) |
| N-11 | Native-first vs narrative “police/insurer must OCR” — acceptable when native is genuinely usable (pages 1–3 / insurer) |

OD-01 thresholds remain provisional (matrix nonblocking).

---

## Exit-gate assessment

| Exit criterion | Assessment |
|----------------|------------|
| All reference pages extracted **or** explicitly flagged | **FAIL** — police p4 extracted incompletely but flagged usable (**B-03**); other aliases extracted or correctly native |
| Baselines documented | **PASS** (provisional timings + auditor RSS) |
| Working PaddleOCR on target OS | **PASS** (2.7.3 / 2.6.2 CPU) |
| Automated route/token/Issue evidence | Largely present; undermined by B-01/B-02 lifecycle defects |
| No Phase 4 scope | **PASS** |

---

## Tag suitability

**Not suitable** for `phase-03-audited-pass`.

Stop. Do **not** create or move any Git tag. Do **not** begin Phase 4.

---

## Appendix — gitignored audit artifacts

Under `tmp/audit/` (not committed):

- `adapter_lifecycle.json` / `probe_adapter_lifecycle.py`
- `delete_during_ocr_race.json` / `probe_delete_race.py`
- `reference_deep_dive.json` / `probe_reference_deep.py`
- `long_medical_police_fix.json` / `probe_jackman_police.py`
- `perf_rss.json`
- `uv-sync.txt`, `check-all.txt`, pytest subset logs

Prior implementer probe: `tmp/phase03_reference_acceptance.json` (alias collision noted).
