# ADR 0037 — Provisional OCR noise classification

## Status

Accepted (Correction 5)

## Context

Dense-form OCR emits grid artefacts, symbol-only detections, and isolated field
numbers that should not pollute the provisional reading transcript. Handwriting
must not be claimed as printed text before Phase 5.

## Decision

Classify provisional items as:

- `credible_printed_text`
- `low_confidence_text`
- `isolated_form_number`
- `checkbox_or_symbol_candidate`
- `line_or_grid_artefact`
- `handwriting_candidate_pending_phase_5`
- `unresolved`

Normal transcript publish keeps credible + low-confidence text. Artefacts and
handwriting candidates retain geometry for diagnostics but are not mixed into
reading-order text. No final handwriting classification or HTR model.

## Consequences

- Overlay diagnostics may show suppressed classes behind a development flag.
- `handwriting_assessment` remains `pending_phase_5` at page level.
