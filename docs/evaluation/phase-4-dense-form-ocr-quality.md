# Phase 4 — Dense-form OCR quality evaluation (Correction 5)

## Synthetic corpus expectations

| Case | Fixture intent | Expected |
|------|----------------|----------|
| 1 Clean typed letter | `clean_printable` / letter-like | Primary accepted |
| 2 Billing visual page | ordinary OCR page | Primary accepted when OCR required |
| 3 Dense small labels | dense form profile | Fallback may be required |
| 4 Heavy H/V rules | `dense-ruled-form.pdf` | Grid interference detected |
| 5 Checkboxes / field numbers | symbol separation | Symbols out of reading text |
| 6 Sparse note | sparse profile | Not rejected for sparsity |
| 7 Punctuation/numbers | ordinary | No excessive symbol penalty |
| 8 Handwriting + labels | `handwriting_pending` | Printed evaluated; HW pending |
| 9 Fragmented 960 | synthetic fragmented | Fallback triggered |
| 10 Fallback no improvement | worse 1600 | Primary retained + warning |

## Private police acceptance

Opaque label: `private_police_scan`

Record only: profile, primary/fallback decision, quality status, line/word counts,
fragmentation aggregates, durations, peak RSS, overlay pass/fail.

Never record transcript content.

## How to improve claims

Do **not** declare improvement solely because line or word counts increased.
Prefer lower fragmentation, higher geometry validity, and better CER/WER on
synthetic gold only.
