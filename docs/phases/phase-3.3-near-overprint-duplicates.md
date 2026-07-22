# Phase 3.3 — Near-overprint duplicate detection

**Branch:** `fix/phase-3-near-overprint-duplicates`  
**Base tag (unchanged):** `phase-3-native-extraction-trust-gate-v1.2` (`e24358d`)  
**Corrective tag:** `phase-3-native-extraction-trust-gate-v1.3`

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
  glyphs (catches interleaved doubles without flagging spaced
  `letter` / `bookkeeper` / `100.00`).
- Safe layer selection cleans chars, rebuilds words, recalculates trust;
  ambiguous selection hard-rejects with
  `excessive_near_overprint_duplicates` and empty text.
- High near-overprint ratio overrides a high weighted trust score.
- UI alert for near-overprint rejection uses the required wording.

## Evidence

- Synthetic fixtures for exact, cross-font, vertical/horizontal offset,
  tagged/untagged, partial bold/shadow, and legitimate repeated letters.
- Unit + trust-gate tests green; `scripts/check_all.py` passed.
- Production worker/runner cleaned cross-font fixture to single-copy text
  (accepted) without publishing doubled glyphs.
- Private corpus: opaque evaluate script pass; scan of accepted pages
  found **0** with high adjacent-double ratio under the new detector.
- Exact raw count 3464 was not present in the local private corpus at
  verification time; synthetic near-overprint pages and private accepted
  pages were checked for doubled publication.
- Real `pnpm dev` API smoke: uploaded near-overprint fixture →
  `native_trust_complete` with cleaned single-copy provisional text.

## Out of scope

Phase 4 OCR / backend raster / LLM.
