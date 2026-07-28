# Phase 3.5 — Multi-path near-overprint hard reject

**Corrective branch on Phase 3.** Does not start Phase 4. Does not lower
`native_trust_threshold`.

## Problem

Production pages with substantial near-overprint duplicate layers were still
**accepted** because the Phase 3.4 composite gate was a single AND that required
high `dominant_offset_support_ratio` on one exact 0.25-pt offset bin. Multi-font
and multi-size layers scatter displacement vectors across nearby bins, so support
stayed low even when coverage and match counts were decisive. A diluted global
near-overprint ratio could also miss a fully duplicated region on an otherwise
clean page.

## Diagnostic — prior gate vs production metrics (no private text)

Defaults: `matched >= 24`, `near_ratio > 0.08`, `coverage > 0.70`,
`support >= 0.55`, span (`word >= 3` OR `line >= 2` OR coverage ≥ 0.90 with
matches ≥ 8).

### Page 3

| Metric | Value | Threshold | Pass/Fail | Mandatory (3.4) |
|--------|-------|-----------|-----------|-----------------|
| matched_near_duplicate_count | 150 | ≥ 24 | PASS | yes |
| near_overprint_duplicate_ratio | 0.327 | > 0.08 | PASS | yes |
| duplicate_layer_coverage_ratio | 1.0 | > 0.70 | PASS | yes |
| dominant_offset_support_ratio | 0.10 | ≥ 0.55 | **FAIL** | **yes (blocked)** |
| span_ok | expected PASS (coverage shortcut) | — | PASS | yes |
| **Final hard_rejection** | | | **FALSE** | |
| Outcome | trust ≈ 0.764 ≥ 0.75 → accepted with doubled text | | | |

### Page 5

| Metric | Value | Threshold | Pass/Fail | Mandatory (3.4) |
|--------|-------|-----------|-----------|-----------------|
| matched_near_duplicate_count | 335 | ≥ 24 | PASS | yes |
| near_overprint_duplicate_ratio | 0.058 | > 0.08 | **FAIL** | **yes (blocked)** |
| duplicate_layer_coverage_ratio | 1.0 | > 0.70 | PASS | yes |
| dominant_offset_support_ratio | 0.075 | ≥ 0.55 | **FAIL** | **yes (blocked)** |
| span_ok | expected PASS | — | PASS | yes |
| **Final hard_rejection** | | | **FALSE** | |
| Outcome | trust ≈ 0.851 ≥ 0.75 → accepted with doubled text | | | |

Page 3 was blocked only by single-offset support. Page 5 was blocked by both
single-offset support and a diluted global near-ratio.

## Fix

- Tolerant offset clustering (absolute + size-relative); top-K cluster support is
  informational for collapse, **not** a mandatory hard AND.
- Demote `dominant_offset_support_ratio` to informational only.
- Independent hard paths:
  - **PATH A** — widespread page duplication (catches page-3 style).
  - **PATH B** — coherent partial duplicate layer / severe regions (catches
    page-5 style without requiring high global near-ratio).
  - **PATH C** — safe layer collapse when one coherent layer is selectable;
    otherwise `visual_authority`.
- Line/region duplicate metrics with floors so sparse bold/shadow does not reject.
- Geometry-first interleaved-duplicate publish invariant before accept.
- Structured hard-rule explanation for DEV inspection.
- Weighted trust score cannot override a fired hard path.

## PATH B (tightened — phase3-v1.6 / Correction 2)

PATH B detects a **coherent partial duplicate layer** with structural evidence.
Sparse near-overprint character matches alone are not enough.

Mandatory Path B conditions (all must pass):

1. Coverage gate: `duplicate_layer_coverage_ratio >= 0.90` **or**
   (`coverage > 0.70` **and** `duplicate_region_count >= 1`).
2. Match count: `matched_near_duplicate_count >= path_b_min_matches` (default 48).
   Adaptive lowering is allowed **only when** duplicate lines/regions already
   satisfy the structure rule below.
3. Structure: `duplicate_line_count >= 2` **or** `duplicate_region_count >= 1`.
4. Geometric overlap: at least one near-overprint pair.

Informational only: dominant / top-K offset support. These never decide Path B alone.

A page with ~22 matched characters and zero duplicate lines/regions **must not**
satisfy Path B. There is **no** silent short-page Path B exception; Path A retains
its short-page match-floor reduction for widespread short pages.

Decision and UI explanation consume one canonical `DuplicateLayerEvidence` object
(`policy_version=phase3-v1.6`). Selected path cannot disagree with mandatory rule rows.

## Evidence

- Unit tests: PATH A with low dominant support; PATH B with diluted near-ratio;
  multi-cluster offsets; geometric interleave vs legitimate repeats; sparse
  bold/shadow non-reject; Correction 2 Path B structure / sparse-match rejection.
- Synthetic worker regressions: `multi-displacement-clusters`,
  `diluted-coverage-duplicate-region`, `billing-duplicate-routing-cases`.
- Private worker regression for pages 3/5: configure
  `near_overprint_multi_cluster` in the gitignored local manifest (skip if
  absent). Assertions never print private text.
- Opaque private evaluate script pass.
- Contracts regenerated (`phase3-v1.6` policy version).

## Out of scope

OCR, backend rendering, LLM (Phase 4+). Lowering `native_trust_threshold`.
