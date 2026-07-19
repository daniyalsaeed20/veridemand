# Phase 3 Completion Report — OCR and Page Quality

**Date:** 2026-07-20  
**Branch:** `phase-03-ocr-page-quality`  
**Starting Phase 2 audited baseline:** tag `phase-02-audited-pass` @ `8930b3259cc076e1c308eefb24cb69f8a79bd08e` (docs tip included `bf25cda`)  
**Verdict:** **PASS WITH GAPS**

---

## 1. Requirements implemented

| FR | Status |
|----|--------|
| FR-EXT-03 | Done — OCR pages rendered via `pdfium_runtime.render_page` at configured DPI |
| FR-EXT-04 | Done — selective preprocess + one retry; deterministic better-pass selection |
| FR-EXT-05 | Done — sole PaddleOCR adapter (`paddleocr==2.7.3` / `paddlepaddle==2.6.2`, CPU) |
| FR-EXT-06 | Done — OCR tokens/spans share `SourceToken` / `SourceSpan` with `method=ocr` |
| FR-EXT-07 | Done — page quality flags + `extraction.*` Issues; no invented text on failure |

Preserved Phase 2: B-01 PDFium sole-import boundary; B-02 native usability gate; LibreOffice path.

---

## 2. Contract changes

- Closed `OcrStatus`: `not_needed` \| `pending` \| `done` \| `failed`
- Added `native_max_cid_ratio` (default `0.05`) and `ocr_force_for_tests` to AppSettings
- Additive quality flags: `low_confidence`, `duplicate_detections`, `duplicate_page`
- Regenerated JSON Schema + Zod; drift gate green
- `contracts_version` remains `0.1`

---

## 3. OCR dependencies and licences

| Package | Version | Licence |
|---------|---------|---------|
| paddleocr | 2.7.3 | Apache-2.0 |
| paddlepaddle | 2.6.2 | Apache-2.0 |
| opencv-python-headless | 4.9.0.80 | Apache-2.0 |
| numpy | ≥1.23,<2 | BSD-3-Clause |
| setuptools | ≥65 (Paddle import requirement) | MIT |
| psutil | locked | BSD-3-Clause |

See [`DEPENDENCY_INVENTORY.md`](../../DEPENDENCY_INVENTORY.md). OD-15 (CPU) and OD-16 (pin A) resolved in [`open-decisions.md`](../readiness/open-decisions.md).

**Model cache:** `%LOCALAPPDATA%/VeriDemand/paddleocr` (override `VERIDEMAND_OCR_MODEL_DIR`). Weights not committed. Health `ocr_enabled` uses importlib find_spec (no model load).

---

## 4. Architecture

- **Adapter:** [`backend/app/services/ocr/adapter.py`](../../backend/app/services/ocr/adapter.py) — sole paddle* importer; lazy CPU init; process-wide single-worker lock; cancel; metrics.
- **Orchestration:** [`ocr_page.py`](../../backend/app/services/extraction/ocr_page.py), [`preprocess.py`](../../backend/app/services/extraction/preprocess.py), [`ocr_quality.py`](../../backend/app/services/extraction/ocr_quality.py).
- **Process:** background thread after `POST /process`; clients poll `GET .../events`.
- **Issues:** session-scoped `Issue` list; `GET .../issues`; OCR retry `POST .../pages/{n}/ocr/retry`.

### Lock order

```text
Verify session/document → render (PDFium lock) → release PDFium
→ preprocess → OCR (OCR worker lock) → re-verify generation
→ commit artifacts | discard
```

Never hold PDFium lock during OCR; never hold SessionService lock during render/OCR.

---

## 5. Routing / artifact policy

| Route | Behavior |
|-------|----------|
| native | Keep native tokens/spans; `ocr_status=not_needed` |
| ocr | Suppress native evidence; OCR; publish OCR tokens/spans; clear `awaiting_ocr` |
| manual_review | No fabricated text; page-quality Issue |
| `OCR_FORCE_FOR_TESTS` | Test-only forced OCR; separate from production routing |

Reprocess atomically replaces per-page OCR artifacts.

---

## 6. Coordinate transformation

Rendered-image pixel polygons → canonical top-left `[0,1]` via `image_polygon_to_normalized`. Degenerate/large-OOB boxes rejected. Spans inherit token method for viewer highlights.

---

## 7. Quality policy (page-level)

Multi-signal assessment (mean conf, printable/control ratios, coverage, overlap/duplicates, critical-looking string **warnings only**). Outcomes: usable / usable-with-warning / low-confidence / failed / blank. Fact-level Green/Amber/Red deferred to Phase 5.

---

## 8. Automated tests

| Suite | Result |
|-------|--------|
| Backend pytest | **147 passed** |
| Frontend vitest | **9 passed** |
| `node scripts/check-all.mjs` | **PASS** (format, lint, mypy, tests, contracts×2, FE build) |

New coverage includes OCR import boundary, adapter serialization/cancel, coordinates/quality, Phase 3 integration (routing, issues, two-session OCR queue, delete-during-OCR, reprocess).

---

## 9. Reference-package aggregates (safe aliases)

Local package present. Private filenames omitted.

| Alias | Pages | Native | OCR routed | OCR ok | Warn | Fail | Tokens | Notes |
|-------|------:|-------:|-----------:|-------:|-----:|-----:|-------:|-------|
| ecw_medical | 24 | 24 | 0 | 0 | 0 | 0 | 0 | **24/24 native** preserved |
| ecw_billing | 1 | 0 | 1 | 1 | 1 | 0 | 136 | OCR filled previously empty native |
| police | 4 | 3 | 1 | 1 | 0 | 0 | 6 | Mostly native-first |
| insurer | 1 | 1 | 0 | 0 | 0 | 0 | 0 | Native text layer |
| long_medical | 6 | 6 | 0 | 0 | 0 | 0 | 0 | Native on sampled pages |

Raw probe: `tmp/phase03_reference_acceptance.json` (gitignored).

---

## 10. Performance (provisional, developer machine)

| Metric | Observed |
|--------|----------|
| Model download + first OCR (billing) | ~37 s wall (includes first-time weight download) |
| Subsequent OCR page (police routed) | ~1.6 s OCR + ~90 ms render |
| Native eCW medical 24 pages | ~3.7 s total native extract |
| OCR workers | 1 |
| DPI | 200 (retry 300 available) |

Spike band ~4–11 s/page remains a comparison only — **no invented pass SLA**.

---

## 11. Manual highlight evidence

Synthetic OCR tokens highlight via existing PDF.js normalized overlays. Native pages unchanged. UI labels **Native** vs **OCR** and states OCR confidence is recognition quality, not legal verification. Synthetic screenshots not required for this report.

---

## 12. Known limitations / gaps

1. **Police/insurer “must OCR” vs native-first:** Production routing stays native-first; many reference police/insurer pages have usable native text. OCR path proven on billing + OCR-routed pages / forced-test mode. Documented conflict.
2. **Handwriting:** flag/issue path only; no universal handwriting recognizer.
3. **Peak RSS** not instrumented in the acceptance script (psutil available for follow-up).
4. **Duplicate-page** detection is heuristic; full FR-EXT-07 duplicate-page Issue catalog coverage is provisional.
5. First OCR after clean cache is dominated by model download/init.

---

## 13. Deferred work

- Phase 4+ classification, facts, chronology, billing interpretation, LLM, demand, export
- GPU optional experiment
- PaddleOCR 3.x re-spike
- Firm-approved gold calibration (OD-01 remains soft for honest threshold claims)

---

## 14. Specification conflicts (recorded)

See plan resolutions: ocr_status vocabulary (contracts win); Issue vs ReviewQueue (Issue); CID ratio default 0.05; background process; native-first vs “police must OCR” acceptance language.

---

## 15. Exit-gate evidence

- All synthetic automated gates green.
- Reference pages extracted **or** explicitly flagged/routed; eCW medical 24/24 native; eCW billing OCR success.
- Measured provisional baselines filled in `03-ocr-thresholds.md`.
- Working PaddleOCR 2.7.3 runtime on Windows CPU (OD-16).

**Final verdict: PASS WITH GAPS** (gaps above; not a FAIL on exit gate blockers).

---

## 16. Stop condition

Phase 3 implementation complete. Tag `phase-03-audited-pass` **not** created. Phase 4 **not** started.
