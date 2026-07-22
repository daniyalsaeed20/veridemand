# Phase 3 implementation report

**Date:** 2026-07-22  
**Branch:** `phase/3-native-extraction-trust-gate`  
**Base tag:** `phase-2-canonical-viewer-coordinates-v1.1` (`da4f4df`)  
**Tag:** `phase-3-native-extraction-trust-gate-v1` (annotated; peels to this branch tip)

## Summary

Native PDF character/word extraction with pdfplumber, pypdf structural
inspection, conservative trust scoring, whole-document escalation, accepted-only
publication, native APIs, and viewer inspection. Progress advances to 35%.

## Non-scope

No backend rasterisation, OCR, layout, HTR, LLM, search, final export, or
persistent storage. Visual agreement is not evaluated.

## Dependencies

| Package | Version | Role |
|---|---|---|
| pdfplumber | 0.11.9 | Native extraction |
| pdfminer.six | 20251230 | Transitive text engine |
| pypdf | 5.9.0 | Structural inspection |
| pypdfium2 | 5.12.1 | Transitive unused |

## Trust policy

- Version: `phase3-v1`
- Threshold: 0.75
- Document failure ratio: 0.30
- Visual agreement: null / `not_evaluated_phase_3`

## Architecture / ADRs

- `docs/architecture/phase-3-native-extraction.md`
- ADRs 0013–0016

## Phase boundary confirmation

Phase 4 has not started.
