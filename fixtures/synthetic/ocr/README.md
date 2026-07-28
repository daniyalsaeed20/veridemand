# Synthetic printed OCR fixtures

Minimal printable assets for Phase 4 CER/WER/IoU calibration.
Not firm-approved legal gold. See docs/evaluation/phase-4-printed-ocr-baseline.md.

## Correction 1

`sparse-embedded-form-2page.pdf` — two-page scanned form with a sparse hidden
OCR text layer. Used to assert that embedded OCR authority is not granted when
candidate coverage is inadequate (expects full visual OCR fallback).
Generate with `python scripts/generate_sparse_embedded_form_fixture.py`.
