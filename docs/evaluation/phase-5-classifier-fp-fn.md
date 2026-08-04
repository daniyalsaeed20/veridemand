# Phase 5 classifier FP/FN categories

Privacy-safe aggregate categories from source-group-isolated out-of-fold
predictions. **No crop IDs, paths, text, or screenshots.** Public ASAP samples
are excluded from these counts.

## Task B2 three-class baseline (superseded for safety evaluation)

Decision: `SUPPLEMENTED MODEL STILL NOT SAFE FOR INTEGRATION`

| Category (asap_medium argmax) | Count |
|-------------------------------|------:|
| handwritten predicted printed | 12 |
| handwritten predicted non_text | 7 |
| printed predicted handwritten | 8 |
| printed predicted non_text | 12 |
| non_text predicted printed | 6 |

Slice failures included signature → non_text on best candidates.

## Task B3 dual-risk (safety-first)

Decision: `SAFETY-FIRST MODEL STILL NOT SAFE`

Best threshold candidates (project OOF):

| Config | HW→printed | HW→non_text | NT→printed | Notes |
|--------|----------:|------------:|-----------:|-------|
| weighted_bce | 20 | 2 | 1 | leaks + slice fails |
| asymmetric_bce | 13 | 1 | 3 | better HW recall; still leaks |
| focal | 0 | 0 | 0 | safety counts clear; printed retention 0.19 |

Failing slice keys recorded across configs:
`cursive_printed`, `signature_printed`, `signature_non_text`,
`handwritten_to_printed`, `handwritten_to_nontext`.

Focal achieves zero cursive/signature unsafe routes only under near-universal
abstention (not a valid production candidate).

Uncertain challenge routing was not final-fitted (gates failed before package
export). Challenge crops remain unused for training.

## Privacy

Aggregates only. No private IDs, paths, visible text, or image montages.
