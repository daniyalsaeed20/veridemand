# Phase 5 — Page-level vision-reservation feasibility (Task C2)

## Decision

```text
PAGE-LEVEL VISION FALLBACK FEASIBLE
```

At least one simple deterministic rule covers all **55** confirmed handwriting
seeds and all **7** remaining Task C1 detector misses using evidence already
present before Phase 6, without private document identity.

Recommended next implementation path (not implemented here):

```text
hybrid page reservation + region router
```

Reserve qualifying pages for Phase 6 while allowing detected printed regions to
keep local recognition, provided a safe region classifier blocks handwritten and
uncertain detections from Paddle.

## Scope and method

Read-only policy audit. No fallback implementation, no detector fine-tune, no
Paddle modification, no router integration, no vision-provider call, no Phase 6.

Evidence used:

- Phase 5 private corpus: 215 pages / 6 documents / 6 source groups
- 55 active human-confirmed handwriting seeds on **9** pages
- Task C0 detector-first region geometries (including duplicate rows so published
  C0 coverage is reproducible)
- Task C1 best candidate re-detected on seed pages only
  (`merged_mobile_recall_bias_plus_server_defaults`) into memory / temp — private
  calibration reports were not rewritten
- Native routing-only join from source PDFs (proposed route, image-dominant,
  native-trust) keyed by document + page index

Private page audit rows stayed under gitignored `temp/`. This document contains
aggregates only.

## Baselines preserved

### Task C0

| Metric | Value |
|--------|------:|
| Confirmed handwriting regions | 55 |
| Detected | 36 |
| Missed | 19 |
| Recall | 0.655 |

### Task C1 best incomplete candidate

| Metric | Value |
|--------|------:|
| Label | `merged_mobile_recall_bias_plus_server_defaults` |
| Detected | 48 |
| Missed | 7 |
| Recall | 0.873 |
| Signature misses | 6 |
| Hand-print misses | 1 |

Re-detect on the 9 seed pages reproduced these aggregates (≈431 s detector time).

## Page evidence (aggregates)

| Aggregate | Value |
|-----------|------:|
| Pages | 215 |
| Pages with confirmed handwriting seeds | 9 |
| Pages containing C0 misses | 4 |
| Pages containing C1 misses | 3 |
| Routing-joined pages | 215 |

Proposed-route histogram (native routing-only, not live visual worker):

| Proposed route | Pages |
|----------------|------:|
| digital_native | 106 |
| embedded_ocr_verified | 104 |
| full_visual_ocr | 5 |

Source-family histogram:

| Family | Pages |
|--------|------:|
| medical_form | 104 |
| other | 97 |
| billing_ledger | 10 |
| image_document | 2 |
| police_form | 2 |

Other usable signals:

| Signal | Pages |
|--------|------:|
| image_dominant | 107 |
| native_trust_failed | 109 |
| visual_processing_required | 109 |
| any empty recognition | 193 |
| any low-confidence recognition | 207 |
| any rejected recognition | 141 |

### Unavailable on this corpus

Populate `.result.json` files are geometry-stripped visual OCR snapshots
(`source_mode=visual_ocr` on all 215 pages; empty repair regions). The following
live visual-worker fields were **not** evaluable as differentiated page signals:

- live `page_route` / visual `final_route_histogram` from a completed worker run
- printed OCR quality gate / dense-form page profile
- targeted repair used / repair fallback
- provisional `handwriting_pending` counts
- visual quality warnings

Native proposed-route and image-dominance substitutes were derived offline from
the source PDFs without calling a vision LLM and without rewriting private
manifests.

## Safety coverage gates

Primary gates (not weakened):

```text
confirmed handwriting regions covered by page reservation = 55 / 55
remaining Task C1 detector misses covered = 7 / 7
```

Style-slice coverage on the selected rule also reached:

| Slice | Covered |
|-------|---------|
| Cursive | 22 / 22 |
| Signatures | 11 / 11 |
| Digits | 10 / 10 |
| Hand-printed | 10 / 10 |
| Longer notes | 2 / 2 |
| C0 misses | 19 / 19 |
| C1 misses | 7 / 7 |

## Candidate rule table (selected)

Wording: pages without a current confirmed seed are **reserved pages without a
current confirmed seed**, not proven false positives.

| Rule | HW coverage | C1 misses | Pages reserved | Reserve rate | Conservative OCR impact | Hybrid suitability |
|------|-------------|-----------|----------------|--------------|-------------------------|--------------------|
| `image_dominant` (best one-signal / simplest / most selective pass) | 55/55 | 7/7 | 107 | 49.8% | 107 pages lose local OCR; ~8.2k detector regions | Suitable if region router blocks HW |
| `source_family ∈ {medical_form, police_form, image_document}` | 55/55 | 7/7 | 108 | 50.2% | 108 pages | Same |
| `native_trust_failed` | 55/55 | 7/7 | 109 | 50.7% | 109 pages | Same |
| `proposed_route ≠ digital_native` | 55/55 | 7/7 | 109 | 50.7% | 109 pages | Same |
| `formish AND image_dominant` (best two-signal selective) | 55/55 | 7/7 | 107 | 49.8% | 107 pages | Same |
| `native_trust_failed OR image_dominant OR formish` (best three OR) | 55/55 | 7/7 | 110 | 51.2% | 110 pages | Same |
| `empty_ratio ≥ 0.25` (best near-miss one-signal) | 49/55 | 7/7 | 81 | 37.7% | — | Insufficient HW coverage |
| `formish AND empty_ratio ≥ 0.25` (most selective near-miss) | 49/55 | 7/7 | 58 | 27.0% | — | Misses 6 seeds on one page |
| `has_empty OR low OR rejected` alone | fails 55/55 | — | ~211 | ~98% | Too broad even if OR-expanded | Insufficient alone |
| `proposed_route = full_visual_ocr` alone | fails | 0/7 | 5 | 2.3% | — | Insufficient |
| `page_width ≥ 1600` | 55/55 | 7/7 | 215 | 100% | Operationally excessive | Do not use |

Twenty-seven evaluated rules passed the primary gates. The tightest passing
reservation rate observed was **107 / 215 (49.8%)**.

## Best rule

```text
page_vision_reservation = required
  when native image-dominance evidence is true
```

Exact signal: `page_is_image_dominant` from existing native / routing evidence
(same predicate used by Phase 4 embedded-OCR routing).

Why selected:

- Covers **55/55** seeds and **7/7** C1 misses
- One signal; deterministic; no private IDs
- Most selective among passing rules (tied with `formish AND image_dominant`)
- Operationally understandable: image-dominant pages already signal visual risk
- Implementable from evidence present before Phase 6

Equivalent family form (`source_family` in medical/police/image_document) also
passes at 108 pages and is justified because every confirmed seed in this corpus
sits in those families — but image-dominance is preferred as a geometry/layout
risk signal rather than a document-taxonomy-only rule.

### Cost snapshot (best rule)

| Measure | Value |
|---------|------:|
| Pages reserved | 107 |
| Reserve rate | 49.8% |
| Documents / source groups affected | 3 / 3 |
| Pages with known handwriting reserved | 9 / 9 |
| Reserved without current confirmed seed | 98 |
| Page-level recall / precision | 1.00 / 0.084 |
| Phase 6 page volume estimate | 107 |
| Proposed routes among reserved | embedded_ocr_verified 104; full_visual_ocr 3 |
| Approx. page-image storage if copies retained | ~37 MB (mean PNG × 107) |

## Printed OCR impact (estimates only — not implemented)

### Conservative mode

Reserved page → no local recognition; entire page for Phase 6.

- Pages losing local OCR: **107**
- Detected regions losing local recognition: **~8,187**
- Prevents handwriting-to-Paddle leakage on reserved pages even for undetected ink
- Reduces local printed OCR coverage on ~half the corpus

### Hybrid mode

Reserved page → detected printed regions may still use local recognition; page
also reserved for Phase 6.

- Detector-missed handwriting still cannot enter Paddle (never detected)
- Detected handwriting can still enter Paddle unless a safe region router blocks it
- Estimated retainable recognised regions on reserved pages: **~2,640**
- Phase 6 page volume unchanged (**107**)

Because the best rule reserves ≈50% of pages, hybrid mode plus the Phase 5
region router is the better operational trade-off: it meets the core
handwriting-preservation requirement without discarding all printed OCR on
image-dominant pages.

## Strategy comparison

| Strategy | Effort | Extra data | Phase 6 cost | Risk | Meets core req. | In Phase 5? |
|----------|--------|------------|--------------|------|-----------------|-------------|
| 1 Conservative page reservation | Low | None | ~107 pages | Large local-OCR loss | Yes | Yes |
| 2 Hybrid page reservation + region router | Medium | Router labels (already planned) | ~107 pages | Router must block HW/uncertain | Yes | Yes |
| 3 Fine-tune PP-OCRv5 detector | High | Corrected det labels | Lower if zero-miss | Signatures may still miss | Unknown until gate | Yes |
| 4 Page-level handwriting-presence model | High | Page labels beyond 9 positives | Depends on precision | Overfit to private families | Potential | Yes |

**Recommendation (Task C2 audit):** Strategy 2 — hybrid page reservation plus the
existing Phase 5 region-router workstream.

**Task C3 implementation note:** Because region routers remain unsafe (Tasks
B–B4), Task C3 implements Strategy 1 — **conservative** page reservation only.
Hybrid mode is deferred (ADR 0087) until a safe region router exists. The
selected reservation signal remains `page_is_image_dominant`.

## Pareto note

Recognition-status rules alone cannot cover all 55 seeds: the best near-miss
(`empty_ratio ≥ 0.25`, or `formish AND empty_ratio ≥ 0.25`) reaches **49/55**
while covering all 7 C1 misses. Six seeds sit on a page without empty / low /
rejected recognition evidence. Expanding recognition ORs to recover those seeds
jumps reservation toward ~98% of pages — that path is **too broad** even though
coverage would pass. Image-dominance / form-family rules occupy the feasible
middle (~50%).

There is no project-approved hard ceiling on reservation rate; ~50% is reported
as operationally understandable for this private corpus, not as a product SLA.

## Privacy and change confirmation

- No private page, crop, or audit manifest tracked in git
- No private IDs, OCR text, screenshots, or classifier predictions in this report
- No OpenAI / vision-provider call; no external data download
- No production runtime, model, OCR, routing, repair, or Phase 6 code change
- Private calibration / coverage / label artefacts were not rewritten
- Unrelated worktree items left untouched

## Repository snapshot (audit time)

- Branch: `phase-05-handwriting-routing`
- Expected HEAD ancestry includes Task C1 commits through `ff14b0d`
- Documentation-only audit artefact: this file (commit only if explicitly requested)
- No push performed as part of this task

```text
PHASE 5 TASK C2 AUDIT COMPLETE
```
