# OCR / Extraction Thresholds (Module 03 Addendum)

| Field | Value |
|-------|-------|
| `thresholds_version` | `0.1-provisional` |
| Spec | Prototype §9, Appendix D, FR-EXT-* |
| Owning module | [03 Page Analysis and Text Extraction](./03-page-analysis-and-text-extraction.md) |
| Config | [`docs/contracts/entities/app-settings.md`](../contracts/entities/app-settings.md) |

## Purpose and status

Numeric and policy knobs for native-vs-OCR routing, OCR retry, page quality flags, and criticality-aware Green/Amber/Red review. These defaults are **provisional** so Phase 3 can be implemented without guessing magic numbers in code.

**Illustrative samples only:** Files under `docs/example/` may be used later to *measure* baselines. They do **not** define product SLAs or the only acceptable document mix. Measured rows below stay `todo_measure` until ExtractionService runs on real hardware.

**Doctrine:** Prefer free/local OCR (PaddleOCR). No paid DocAI. No single global OCR confidence cutoff (§9.3). LLM is not the primary extractor; vision crop is optional assist only.

---

## 1. Routing decision → functions

Maps prototype §9.1 to proposed helpers in module 03.

| Step | Action | Function(s) | Outcome |
|------|--------|-------------|---------|
| 1 | Native extract | `extract_native_page` / `pdfplumber_extract_words` | words + geometry |
| 2 | Score usability | `score_native_text_usability` | `PageDiagnostics` |
| 3 | Route | `select_page_route` | `native` \| `ocr` \| `manual_review` |
| 4 | OCR render | `render_page_for_ocr` at `ocr_render_dpi` | image |
| 5 | OCR | `run_paddle_ocr` | tokens + confidences |
| 6 | Uncertain? | `should_preprocess` → `preprocess_image` → retry once at `ocr_retry_dpi` | one retry max |
| 7 | Still bad / handwriting | `assess_page_quality` | flags + review issues |
| 8 | Optional crop assist | vision crop (rare) | suggestion only |
| 9 | User | Human review | confirmed value |

**Fail-open rule:** When native usability is ambiguous, prefer **`ocr`** over keeping weak native text (false native is worse than OCR cost).

---

## 2. Native usability knobs (provisional)

Used by `score_native_text_usability` / `select_page_route`. Env names map to `AppSettings`.

| Env / setting | Type | Provisional default | Interpretation |
|---------------|------|---------------------|----------------|
| `NATIVE_MIN_CHARS` | int | `40` | Below this on a non-blank page → lean OCR |
| `NATIVE_MIN_TEXT_COVERAGE` | float | `0.02` | Fraction of page area with text glyphs; below → lean OCR |
| `NATIVE_MAX_REPLACEMENT_RATIO` | float | `0.05` | Replacement/control glyph ratio above → unusable native |
| `NATIVE_MAX_ZERO_WIDTH_OR_OVERLAP_RATIO` | float | `0.15` | Bad word geometry → unusable coordinates |
| `NATIVE_MIN_READING_ORDER_SCORE` | float | `0.55` | Heuristic 0–1; below → OCR or block regroup |
| `NATIVE_LIKELY_SCAN_IMAGE_COVERAGE` | float | `0.60` | Large image area + low text → likely scan |
| `NATIVE_LONG_TOKEN_BAND` | int | `40` | Token length above this counts toward long-token ratio |
| `NATIVE_MAX_LONG_TOKEN_RATIO` | float | `0.20` | With elevated mean/median → pathological tokenization |
| `NATIVE_MAX_MEAN_TOKEN_LENGTH` | float | `24` | Mean token length ceiling (composite / dual-elevation) |
| `NATIVE_MAX_MEDIAN_TOKEN_LENGTH` | float | `18` | Median token length ceiling (composite / dual-elevation) |
| `NATIVE_MIN_PRINTABLE_RATIO` | float | `0.90` | Below → unusable native |
| `NATIVE_MAX_CONTROL_CHAR_RATIO` | float | `0.02` | Above → unusable native |
| `NATIVE_MAX_OVERSIZED_BOX_RATIO` | float | `0.20` | Fraction of tokens with huge page-relative boxes |

**Decision sketch**

```text
if blank_page → route manual_review (or flag blank)
else if pathological_tokenization
      (long_token_ratio > MAX_LONG AND (mean > MAX_MEAN OR median > MAX_MEDIAN))
      OR (mean > MAX_MEAN AND median > MAX_MEDIAN)
      → ocr; flag pathological_tokenization; publish no tokens/spans
else if replacement/control/printable/geometry/CID hard fails → ocr
else if char_count < MIN_CHARS or text_coverage < MIN_COVERAGE → ocr
else if reading_order_score < MIN → ocr
else if image_coverage >= LIKELY_SCAN and text_coverage < MIN → ocr
else → native
```

A single long URL or identifier alone must **not** trip pathological tokenization (median/mean stay low when other tokens are normal prose).

Known-label absence (expected form labels missing) is a **soft** signal: prefer OCR when other scores are marginal; do not alone force `manual_review`.

---

## 3. OCR render / retry (Appendix D)

| Env / setting | Provisional default | Notes |
|---------------|---------------------|-------|
| `OCR_WORKERS` | `1` | Prototype concurrency |
| `OCR_RENDER_DPI` | `200` | First pass |
| `OCR_RETRY_DPI` | `300` | Single retry after light preprocess |
| Max preprocess+OCR retries | `1` | FR-EXT-04 — not indefinite |

Preprocess only when diagnostics warrant (skew/rotation/low contrast). Pause OCR during heavy export if memory constrained (prototype §16).

---

## 4. Page quality flags → issues

| Condition (provisional) | `quality_flags` | `issue_type` | Typical severity |
|-------------------------|-----------------|--------------|------------------|
| Near-zero tokens after native+OCR | `blank` | `extraction.unreadable_page` | red/amber |
| Mean token confidence &lt; `OCR_PAGE_MEAN_CONF_LOW` (default `0.55`) after retry | `low_confidence` | `extraction.low_ocr_confidence` | amber (red if page holds only critical fields) |
| Native layer present but high replacement/garbage | `broken_text_layer` | `extraction.broken_text_layer` | amber |
| Abrupt cutoff / incomplete lines heuristic | `truncated_text` | `extraction.truncated_text` | amber |
| Script/handwriting detector or very irregular strokes | `suspected_handwriting` | `extraction.suspected_handwriting` | red if critical field region |

Additional provisional knobs:

| Env / setting | Default | Notes |
|---------------|---------|-------|
| `OCR_PAGE_MEAN_CONF_LOW` | `0.55` | Page-level mean OCR confidence after best attempt |
| `OCR_PAGE_MEAN_CONF_RETRY_TRIGGER` | `0.70` | Below this after first OCR → allow one preprocess+retry |

Flags **never** silently discard evidence; they create visible review items (FR-EXT-07).

---

## 5. Token / span confidence → review policy (no global cutoff)

Combine: recognition confidence, format validation (date/ID/money parsers), multi-source agreement, and `fact_type` criticality from [`docs/contracts/fact-types.md`](../contracts/fact-types.md).

### Confidence bands (token/span, provisional)

| Band | Token/span confidence |
|------|------------------------|
| High | `>= 0.90` |
| Mid | `0.70 – 0.89` |
| Low | `< 0.70` |

### Review matrix

| Field criticality | High + valid format | Mid + valid format | Low or invalid format | Conflict across sources |
|-------------------|---------------------|--------------------|----------------------|-------------------------|
| **critical** (e.g. `collision.date`, `claim.number`, `client.dob`) | Green if ≥2 sources agree; else Amber | Amber | **Red** | **Red** (never auto-pick) |
| **normal** | Green | Amber optional | Amber | Amber/Red depending on type |

Examples from §9.3: low-confidence address → Amber; low-confidence DOL or claim number → **Red**.

Downstream FactService (module 05) applies this when attaching spans to facts; ExtractionService emits page/token confidence for that policy.

---

## 6. Handwriting path (~1% of cases)

1. Detect `suspected_handwriting` or unreadable crop.  
2. Keep printed label if OCR/native found it.  
3. Leave handwritten **value blank** → targeted review question.  
4. User enters value + optional rectangle (`method: manual`).  
5. Optional vision crop suggestion remains `needs_review` until accepted.

Do not treat handwriting OCR as authoritative.

---

## 7. Measured baselines (fill in Phase 3)

Record on the **developer machine** after ExtractionService exists. If using `docs/example/`, label results **illustrative only**.

| page_class | example source (optional) | median_ms_per_page | p95_ms_per_page | peak_ram_mb | route_mix_native_ocr_manual | status |
|------------|---------------------------|--------------------|-----------------|-------------|-----------------------------|--------|
| native_digital | e.g. digital EMR export pages | | | | | `todo_measure` |
| scanned_typed | e.g. police / insurer scans | | | | | `todo_measure` |
| mixed_long_scan | e.g. long clinical fax stack | | | | | `todo_measure` |
| handwriting_exception | rare pages | | | | | `todo_measure` |

Also log: temp disk peak, OCR worker count, DPI used for retries.

---

## 8. Related contracts

- Page route / methods: [`docs/contracts/enums.md`](../contracts/enums.md) (`PageRoute`, `ExtractionMethod`)  
- Entities: `DocumentPage`, `SourceToken`, `SourceSpan`  
- Issues: `extraction.*` in [`docs/contracts/issue-types.md`](../contracts/issue-types.md)

---

## Changelog

| Version | Date | Change |
|---------|------|--------|
| `0.1-provisional` | 2026-07-18 | Initial knobs and policy matrices (Pass 3); measurements deferred |
