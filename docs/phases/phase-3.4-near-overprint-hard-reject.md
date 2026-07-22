# Phase 3.4 — Near-overprint hard reject

**Branch:** `fix/phase-3-near-overprint-hard-reject`  
**Base tag (unchanged):** `phase-3-native-extraction-trust-gate-v1.3`  
**Corrective tag:** `phase-3-native-extraction-trust-gate-v1.4`

## Problem

Near-overprint soft-penalized `duplication_score` (weight 0.15) so pages with
interleaved doubles could remain **accepted** above the 0.75 threshold with
empty reason codes (example score path ≈ 0.96 → 0.82).

## Fix

- Redefined `near_overprint_duplicate_ratio` as **redundant** overprint chars /
  total.
- Published diagnostics: coverage, match count, dominant offset support,
  word/line span.
- Composite hard evidence forces clean-or-reject; weighted score cannot
  override.
- Safe layer collapse rebuilds words and verifies interleaved doubles are gone.
- Ambiguous selection → `visual_authority`, empty text,
  `excessive_near_overprint_duplicates`.
- Dev inspection panel shows duplicate diagnostics.

## Evidence (opaque)

- Synthetic near-overprint / partial header-footer / full-page duplicate fixtures.
- Unit + trust tests: soft score cannot override composite hard reject.
- Private corpus scan: **0** accepted pages with high interleaved-double ratio;
  opaque evaluate script pass.
- Exact private page with raw count 3464 was not present locally at verification;
  synthetic production-path and private accepted-page scans confirmed no doubled
  publication.
- `scripts/check_all.py` and `pnpm dev` API smoke on cross-font fixture.

## Out of scope

Phase 4 OCR / backend raster / LLM.
