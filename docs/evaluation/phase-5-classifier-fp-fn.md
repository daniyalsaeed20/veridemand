# Phase 5 classifier FP/FN categories (Task B2)

Privacy-safe aggregate categories from source-group-isolated out-of-fold
predictions. **No crop IDs, paths, text, or screenshots.** Public ASAP samples
are excluded from these counts.

## Decision context

`SUPPLEMENTED MODEL STILL NOT SAFE FOR INTEGRATION` — Task B2 ASAP
supplementation improved argmax handwriting recall but did not clear aggregate
plus cursive/signature slice gates. Best reported config for quality:
`asap_medium` (macro F1); best safe-bypass among top candidates:
`asap_medium_project_weighted`.

## Routing / confusion categories (aggregate, asap_medium argmax)

| Category | Count |
|----------|------:|
| handwritten predicted printed | 12 |
| handwritten predicted non_text | 7 |
| printed predicted handwritten | 8 |
| printed predicted non_text | 12 |
| non_text predicted printed | 6 |

Under best threshold candidates, handwritten→printed fell as low as **1–2** but
never reached **0** while holding printed retention ≥80% and 100% safe-bypass.

## Handwriting subtype / slice outcomes

| Slice gate | Result |
|------------|--------|
| cursive → printed = 0 | achievable on medium configs |
| signature → printed = 0 | achievable on project-weighted |
| cursive → non_text = 0 | still fails on some candidates |
| signature → non_text = 0 | **fails** (signatures discarded as non_text) |

Failing slices recorded in decision payload:
`cursive_printed`, `cursive_non_text`, `signature_printed`, `signature_non_text`
(union across configs; project-weighted still fails on signature→non_text).

## Geometry / quality categories

| Category | Observation |
|----------|-------------|
| small crops | some misroutes among low-area crops |
| broad crops | some misroutes among high aspect-ratio line crops |

## Privacy

No private identifiers in this document. ASAP transcription text is not used
and not reported.
