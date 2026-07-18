# OCR Spike Report

**Status date:** 2026-07-19  
**Spike:** [`spikes/ocr/`](../../spikes/ocr/)  
**Stack:** pdfplumber + **pypdfium2** + **PaddleOCR 2.7.3** / PaddlePaddle 2.6.2 (isolated `.venv`) + Pillow overlays  
**Coordinate space:** normalized top-left `[0, 1]`  
**Raw metrics:** `spikes/ocr/out/metrics.json` + `*_overlay.png`

---

## Disclaimer

Results are from a **small set of representative pages** on one developer machine.  
**Do not claim general OCR accuracy** for the product from this spike.  
**No token was promoted to a verified fact** (`verified_fact: false` on all samples).

---

## Runtime finding (important)

| Attempt | Result |
|---------|--------|
| PaddleOCR **3.7** + PaddlePaddle **3.3.1** on Windows | **Failed** at inference with `NotImplementedError` in oneDNN/PIR (`ConvertPirAttribute2RuntimeAttribute`) |
| PaddleOCR **2.7.3** + PaddlePaddle **2.6.2** in spike venv (`numpy<2`) | **Succeeded** |

**Recommendation:** Phase 3 should pin a known-good Windows CPU stack (start from spike pins) and re-validate before upgrading to PaddleOCR 3.x. Record purpose/version/licence when promoted.

---

## Corpus observations (routing)

Contrary to a pure “image-only scan” assumption, several Appendix G “OCR-first” files contain **usable native text layers** on this corpus:

| Document | Auto-route (provisional knobs) | Notes |
|----------|--------------------------------|-------|
| `EG90156.pdf` (police) | **native** (when not forced) | Readable native words (e.g. report headers, case fields) |
| Insurer letter | **native** | Includes claim number / DOL strings in native text |
| Long medical stack | **native** on sampled pages | Typed invoice/chiro pages with text layer |
| eCW medical | **native** | Digital export |
| eCW billing ledger | **ocr** (cid ratio ~0.57) | Broken `(cid:N)` encoding — must not trust native |

Forced OCR was also run on police / insurer / medical pages to measure the OCR path.

---

## Measured results (forced OCR path unless noted)

| Source | Page | Route | Tokens | Mean conf | Total ms | Peak RSS MB | DPI |
|--------|------|-------|--------|-----------|----------|-------------|-----|
| EG90156.pdf | 1 | ocr | 251 | 0.963 | 11143 | 699 | 200 |
| EG90156.pdf | 2 | ocr | 80 | 0.967 | 4245 | 749 | 200 |
| Mayel Amini Dairyland… | 1 | ocr | 42 | 0.967 | 4660 | 841 | 200 |
| MEDICAL RECORDS… JACKMAN | 1 | ocr | 55 | 0.986 | 5008 | 880 | 200 |
| MEDICAL RECORDS… JACKMAN | 2 | ocr | 39 | 0.991 | 7097 | 970 | 200 |
| MEDICAL RECORDS… JACKMAN | 10 | ocr | 48 | 0.947 | 4445 | 1014 | 200 |
| eCW Medical Records | 1 | **native** | 50 | 1.0 | 135 | 1015 | 200 render only |
| eCW Billing Ledger | 1 | ocr | 136 | 0.985 | 6474 | 1015 | 200 |

PaddleOCR engine load ≈ **4.1 s** (warm cache).

Overlays written under `spikes/ocr/out/` for visual QA of polygons.

---

## Failures / warnings

- PaddleOCR 3.x unusable on this host (see above).  
- Provisional native knobs alone **under-detect** “prefer OCR for corpus demos” when a usable text layer exists — that is **correct** for FR-EXT native-first policy, but demos must still exercise OCR on broken layers (billing) and optional quality compares.  
- Added spike heuristic: **cid ratio > 0.25 → OCR** (needed for eCW ledger).  
- Low-confidence critical candidates are flagged in token `review_flag`; never verified.

---

## Recommended initial routing thresholds (calibration starting point only)

Keep [`03-ocr-thresholds.md`](../modules/03-ocr-thresholds.md) provisional defaults, plus:

| Knob | Suggested initial value | Rationale from spike |
|------|-------------------------|----------------------|
| `NATIVE_MIN_CHARS` | 40 (unchanged) | Did not false-trigger on these natives |
| `NATIVE_MIN_TEXT_COVERAGE` | 0.02 (unchanged) | OK |
| **New:** `NATIVE_MAX_CID_RATIO` | **0.25** | Ledger had ~0.57 cid words → must OCR |
| `OCR_RENDER_DPI` | 200 | Worked; mean conf mostly ≥0.94 on samples |
| `OCR_RETRY_DPI` | 300 | Not required on these high-conf pages; keep for mid-conf |
| `OCR_PAGE_MEAN_CONF_RETRY_TRIGGER` | 0.70 | Unchanged |
| `OCR_PAGE_MEAN_CONF_LOW` | 0.55 | Unchanged |
| Critical token band | Mid 0.70–0.89 Amber; &lt;0.70 Red if critical | Unchanged; enforce no auto-verify |

**Fail-open:** when native is ambiguous or cid-corrupted → OCR.

**Long-stack expectation:** ~4–11 s/page OCR on this machine at 200 DPI; ~60-page stack ⇒ multi-minute job (matches prototype §16). Peak RSS approached ~1 GB during sequential OCR pages.

---

## Phase impact

| Phase | Impact |
|-------|--------|
| 0 | Unblocked |
| 2 | Native path feasible on much of Amini package |
| 3 | **Blocked for production adapter until pinned working Paddle stack**; spike proves feasibility with 2.7.3 |
| 6 | Billing ledger needs OCR (or better export) before layout parse |

---

## Artifacts

- `spikes/ocr/out/metrics.json`  
- `spikes/ocr/out/*_overlay.png`  
- `spikes/ocr/.venv/` (local; gitignored)
