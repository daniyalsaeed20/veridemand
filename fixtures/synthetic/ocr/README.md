# Synthetic printed OCR fixtures

Minimal printable assets for Phase 4 CER/WER/IoU calibration.
Not firm-approved legal gold. See docs/evaluation/phase-4-printed-ocr-baseline.md.

## Correction 1

`sparse-embedded-form-2page.pdf` — two-page scanned form with a sparse hidden
OCR text layer. Used to assert that embedded OCR authority is not granted when
candidate coverage is inadequate (expects full visual OCR fallback).
Generate with `python scripts/generate_sparse_embedded_form_fixture.py`.

## Correction 5 — dense-form quality gate

Committed fixtures used by quality/profile tests and evaluation:

| Case | Asset | Expectation |
|------|-------|-------------|
| Clean letter | `clean_printable.pdf` / `clean_*.png` | Primary accepted |
| Dense ruled form | `dense-ruled-form.pdf` | Grid interference / dense profile |
| Large grid | `large-grid-page.pdf` | Grid signals |
| Handwriting pending | `handwriting_pending.png` | Printed evaluated; HW pending Phase 5 |
| Sparse / table / noise | `empty_page`, `simple_table`, `light_noise` | Profile-calibrated gates |

Synthetic fragmented primary and no-improvement fallback cases are covered by
unit tests and `scripts/evaluate_correction5_ocr_quality.py` (no private text).
