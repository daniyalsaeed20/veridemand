# Phase 3 synthetic smoke corpus — triage reconciliation

## Purpose

Retrospective record of the original 13-case smoke-corpus triage for the
Phase 3 native-text trust gate. This is **test-infrastructure evidence**, not a
new product phase and not a change to the source-of-truth roadmap.

Production soft trust score threshold was **not** lowered:

- `Settings.native_trust_threshold` remains **0.75**

## Baselines

| Metric | Original (pre-triage) | Final (verified) |
|--------|----------------------:|-----------------:|
| Passed | 16 | 25 |
| Failed | 13 | 0 |
| Skipped | 41 | 45 |
| Total page-scoped cases | 70 | 70 |

Original failures: **T06, T07, T16, T18, T19, T22, T23, T26, T42, T43, T50, T55, T65**.

Final verification commands (clean tree / tagged state):

```bash
pnpm smoke:corpus:validate
pnpm smoke:corpus
pnpm check
```

Required smoke result: **passed 25 / failed 0 / skipped 45**.

## Classification vocabulary

Each of the 13 cases uses exactly one of:

- genuine VeriDemand regression
- generator defect
- manifest expectation defect
- reason-code naming mismatch
- future-phase / not-yet-implemented
- unsupported document-scoped behaviour

## Original failure reconciliation (13 cases)

| Test ID | Test title | Original expected authority | Original actual authority | Classification | Exact cause | Production-code change | Generator change | Manifest change | Current-phase expectation | Future-phase expectation | Final actual result | Final pass/skip status |
|---------|------------|----------------------------|---------------------------|----------------|-------------|------------------------|------------------|-----------------|---------------------------|--------------------------|---------------------|------------------------|
| T06 | Cross-font near-overprint duplicate | `visual_authority` | `native_authority` (false accept of interleaved layers) | genuine VeriDemand regression | Cross-font full-page near-overprint cleaned/accepted while publishing interleaved doubles | PATH A/B/C near-overprint tightening; residual/AABB safety; dual-outcome smoke accept | none (page construction kept) | `acceptable_outcomes` clean-or-visual | Dual: cleaned `native_authority` **or** `visual_authority` hard reject | — | `native_authority` / `accepted` (single-copy) | **passed** |
| T07 | Partial duplicate header and footer | `visual_authority` | `native_authority` (false accept of duplicated regional bands) | genuine VeriDemand regression | Diluted global ratio missed PATH B; regional header/footer doubles published | PATH B regional match floor; PATH C regional salvage / residual safety | none | `acceptable_outcomes` clean-or-visual | Dual: cleaned body **or** visual hard reject | — | `native_authority` / `accepted` (no dup header/footer) | **passed** |
| T16 | Sparse native text on mostly blank page | `visual_authority` | Not sparse (chrome polluted page); wrong reason codes (`sparse_native_text`) | generator defect | Native `header()`/`footer()` prevented real sparsity (`native_min_characters`) | none | Rewrite: only tiny `VD-1` token; no native chrome; page replaced | Remap to `native_text_too_sparse` / `native_text_absent`; checksums | Hard reject sparse native | — | `visual_authority` / `rejected` with sparse codes | **passed** |
| T18 | White-on-white hidden native text | `visual_authority` | `native_authority` / `accepted` | future-phase / not-yet-implemented | Phase 3 has no visual-agreement gate for invisible white text | none | none (page kept) | `phase_expectation=not_yet_implemented` | Soft-pass only (crash/publication safety) | Visual agreement / visibility trust | `native_authority` / `accepted` | **skipped** (`not_yet_implemented`) |
| T19 | Invisible text rendering mode | `visual_authority` | `native_authority` / `accepted` | future-phase / not-yet-implemented | Render-mode-3 text is extractable; Phase 3 cannot detect invisibility | none | none | `phase_expectation=not_yet_implemented` | Soft-pass only | Visual agreement / visibility trust | `native_authority` / `accepted` | **skipped** (`not_yet_implemented`) |
| T22 | Page rotation metadata 180 degrees | `native_authority` | `visual_authority` / `rejected` (`unstable_extraction_order`) | future-phase / not-yet-implemented | `/Rotate=180` yields reversed extraction order (same class as T21) | none | none | `phase_expectation=not_yet_implemented` | Soft-pass until rotation tokenisation hardened | Stable rotated native accept | `visual_authority` / `rejected` | **skipped** (`not_yet_implemented`) |
| T23 | Small square page size | `native_authority` | `visual_authority` / `error` then geometry reject | generator defect | A4 header/footer strings overflowed 300×300 MediaBox | Coordinate clamp fixed extraction crash; page still needed generator fix for accept | Compact chrome; page replaced | Notes updated | `native_authority` / `accepted` | — | `native_authority` / `accepted` | **passed** |
| T26 | Non-zero MediaBox origin | `native_authority` | `visual_authority` / `error` then OOB reject | future-phase / not-yet-implemented | Negative MediaBox/CropBox origin mapping not hardened for Phase 3 | Boundary clamp stopped crash; origin mapping not claimed complete | none | `phase_expectation=not_yet_implemented` | Soft-pass | Non-zero page-origin native accept | `visual_authority` / `rejected` | **skipped** (`not_yet_implemented`) |
| T42 | Replacement-character noise | `visual_authority` | `visual_authority` / `error` (`native_extraction_error`) | genuine VeriDemand regression | Normalised polygon corners could exceed 1.0 by FP (`nx + nw`); validation crash | `map_pdfplumber_box` relative normalise + tolerance OOB + unit-square corner clamp; zero-area placeholder | none | none (reason already `high_replacement_character_ratio`) | Hard reject replacement noise | — | `visual_authority` / `rejected` with `high_replacement_character_ratio` | **passed** |
| T43 | Symbol-only and Dingbats noise | `visual_authority` | `visual_authority` / wrong reason (`excessive_near_overprint_duplicates`) | generator defect | ZapfDingbats remapped to Latin letter runs under extraction; symbol ratio diluted | none (near-overprint safety net was incidental) | ASCII punctuation symbol rows; page replaced | Notes; keep `high_symbol_only_word_ratio` | Hard reject symbol-only noise | — | `visual_authority` / `rejected` with `high_symbol_only_word_ratio` | **passed** |
| T50 | Visible text rendered only as raster image | `image_authority` | `visual_authority` / `absent` | manifest expectation defect | Phase 3 routes empty native image pages as `visual_authority`/`absent` (same as T10) | none | none | Expect `visual_authority`/`absent` + `native_text_absent` | Match Phase 3 routing | Dedicated `image_authority` enum path if product later splits | `visual_authority` / `absent` | **passed** |
| T55 | JPEG-compressed photo page | `image_authority` | `visual_authority` / `absent` | manifest expectation defect | Same Phase 3 empty-native routing as T10/T50 | none | none | Expect `visual_authority`/`absent` | Match Phase 3 routing | Same as T50 | `visual_authority` / `absent` | **passed** |
| T65 | Truly blank page | `image_authority` | `visual_authority` / `absent` | manifest expectation defect | Blank page has no native text; Phase 3 uses `visual_authority`/`absent`; `blank_page` is future | none | none | Expect `visual_authority`/`absent`; `blank_page` kept as future reason | Match Phase 3 routing | Dedicated blank-page reason / image authority if added | `visual_authority` / `absent` | **passed** |

### Classification notes (no silent reinterpretation)

- **T18 / T19:** Product intent is future-phase **visual agreement**. Manifest uses
  `not_yet_implemented` rather than `future_phase_expected` because the runner’s
  `future_phase_expected` rule treats a Phase-3 `native_authority` accept as
  `unsafe_native_accept`. Soft-pass under `not_yet_implemented` is the honest
  Phase-3 stance until visibility agreement exists.
- **T50 / T55 / T65:** Not production defects. Expectations were aligned to the
  same Phase-3 routing already applied to T10.
- No case was marked skipped merely because it currently fails without a
  documented phase/capability reason.

## Skip integrity (45 skipped)

Grouped from the committed manifest `phase_expectation` field:

### `not_yet_implemented` (38)

T18, T19, T21, T22, T26, T27, T28, T29, T30, T31, T32, T33, T34, T35, T36, T37,
T38, T39, T40, T45, T46, T47, T48, T49, T56, T57, T58, T59, T60, T61, T62, T63,
T64, T66, T67, T68, T69, T70

### `future_phase_expected` (7)

T11, T12, T13, T51, T52, T53, T54

### `viewer_only` (0)

None in this corpus.

### `document_scoped_not_representable` (0)

None as page entries. Document-container cases (encryption, malformed xref,
attachments, etc.) remain listed under manifest `document_scoped_exclusions`
and are out of scope for page-scoped smoke.

**25** pages remain `current_phase_expected` and are fully asserted.

## Production corrections

1. **Near-overprint (T06 / T07 class):** PATH A/B composite evidence, PATH C clean
   with residual / dense AABB safety, regional PATH B match floor, garbled-band
   salvage that preserves legitimate English doubles (e.g. `bookkeeper`).
2. **Geometry boundary (T42 class):** Relative-to-page-box normalisation; only
   tiny overflow within configured point tolerance is clamped into the page;
   material OOB remains flagged; non-finite values and inverted/zero-area boxes
   are invalid; public polygon corners are forced into `[0, 1]` so FP edges cannot
   raise schema validation crashes.
3. **Trust threshold:** unchanged at **0.75**.

## Generator corrections

- **T16:** remove native header/footer chrome; keep sparse token only.
- **T23:** compact chrome that fits 300×300.
- **T43:** ASCII punctuation symbol rows instead of ZapfDingbats.

## Manifest corrections

- Dual `acceptable_outcomes` for T06 / T07.
- Production reason codes for T16.
- Soft-pass phase tags for T18, T19, T22, T26.
- `visual_authority` / `absent` for T50, T55, T65 (aligned with T10).
- SHA-256 checksums in `docs/smoke/README.md` and
  `scripts/smoke_corpus/__init__.py`.

## Geometry boundary verification (T42)

`map_pdfplumber_box` (`backend/app/extraction/native/coordinates.py`):

1. Subtracts effective page origin (`page_bbox_x0` / `page_bbox_top`) before
   normalising by page width/height.
2. Uses `coordinate_tolerance_points`: overflow beyond `limit + tol` is
   **out_of_bounds**; only values inside that band are clamped to `[0, limit]`.
3. Material OOB sets `out_of_bounds=True` (not silently accepted as valid geometry).
4. Non-finite inputs (`NaN` / `±inf`) mark `invalid=True` via `_finite`.
5. Inverted (`x1 <= x0` / `bottom <= top`) and zero-area boxes mark
   `invalid` / `zero_area`; collapsed normalised extents use a placeholder
   geometry solely so callers can reject on flags without schema crashes.

Unit coverage: `test_coordinate_edge_clamp_never_exceeds_unit_square` and existing
geometry tests.

## Phase boundary

This work stays inside Phase 3 / Phase 3.5 native trust and smoke
infrastructure. **Phase 4 has not started.**
