# Phase 4 — Targeted repair evaluation (Correction 6)

## Synthetic fixtures

Committed under `fixtures/synthetic/ocr/targeted-repair/` (A–J). Regenerate:

```bash
uv run python scripts/generate_targeted_repair_fixtures.py
```

| ID | Expectation |
|----|-------------|
| A | Targeted repair (one wrong word) |
| B | Targeted repair / local detection if shifted |
| C | Header-only repair |
| D | Footer-only repair |
| E | Two distant regions |
| F | Full visual OCR (large defect) |
| G | Full visual OCR (scattered) |
| H | `embedded_ocr_verified` |
| I | Full visual OCR (image-only) |
| J | Repair with HW pending Phase 5 |

## Quality comparison

For reviewed synthetic pages compare base candidate vs targeted repair vs
full-page OCR on: CER, WER, numeric-token accuracy, region recall/precision,
geometry alignment, duplicate overlap, retained-word preservation.

Targeted repair passes only when the defective region improves without damaging
unaffected retained content.

## Private evaluation

- Billing (`private_billing_document`): routing-only audit first; process repair
  only if eligibility evidence passes. Do not force repair.
- Embedded OCR corpus (`private_medical_embedded_ocr`): focused opaque pages with
  high / local / widespread disagreement — aggregates only.

## Performance

Record routing, clustering, crop, recognition, local detection, reconciliation,
publication, and total repair duration vs full-page OCR on the same synthetic
pages. Correctness is mandatory; no required speed percentage.
