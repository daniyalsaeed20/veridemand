# Phase 3.3 — Near-overprint duplicate detection

**Branch:** `fix/phase-3-near-overprint-duplicates`  
**Base tag (unchanged):** `phase-3-native-extraction-trust-gate-v1.2` (`e24358d`)  
**Corrective tag:** `phase-3-native-extraction-trust-gate-v1.3` (after private verification)

## Problem

Cross-font / near-offset duplicate text layers survived
`dedupe_chars(tolerance=1, extra_attrs=("fontname", "size"))`, so
`duplicate_character_ratio` stayed ~0 and pages could be accepted with
interleaved doubled native text.

## Fix

- Retain strict pdfplumber dedupe metric as `strict_duplicate_ratio`
  (alias `duplicate_character_ratio`).
- Add cross-font near-overprint pairing (IoU / centre distance / size
  similarity; no fontname equality required).
- Detect complete duplicate layers via font / size / tagged partitions
  with identical reading-order text, plus reading-order adjacent near
  glyphs (catches interleaved `RRuunn` without flagging spaced
  `letter` / `bookkeeper` / `100.00`).
- Safe layer selection cleans chars, rebuilds words, recalculates trust;
  ambiguous selection hard-rejects with
  `excessive_near_overprint_duplicates` and empty text.
- High near-overprint ratio overrides a high weighted trust score.

## Evidence

- Synthetic fixtures for exact, cross-font, vertical/horizontal offset,
  tagged/untagged, partial bold/shadow, and legitimate repeated letters.
- Unit + trust-gate tests green.
- Private corpus: no accepted page with high adjacent-double ratio under
  the new detector; opaque evaluate script pass.
- Exact raw count 3464 was not present in the local private corpus at
  verification time; synthetic near-overprint pages and private accepted
  pages were checked for doubled publication.

## Out of scope

Phase 4 OCR / backend raster / LLM.
