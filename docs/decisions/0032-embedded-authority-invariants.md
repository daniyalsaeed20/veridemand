# 0032 — Embedded OCR authority invariants

## Status

Accepted

## Context

Phase 4.5 could grant `embedded_ocr_authority` after visual agreement while
publishing an empty visual page result (`visual_result_available=false`,
zero words/lines). Document status became `not_required`, and the UI labelled
the page “Printed visual OCR” even though Paddle OCR never ran. Verification
candidates remained quarantined and were never materialised as public results.

## Decision

A page finishes as exactly one terminal `page_result_state`:

- `digital_native`
- `embedded_ocr_verified`
- `embedded_ocr_targeted_repair`
- `full_visual_ocr`
- `visual_no_text`
- `page_failed`

`embedded_ocr_verified` requires completed visual agreement, materialised
verified public words/lines with validated geometry, and
`visual_result_available=true`. Quarantined `verification_words` are never
public authority. Nonblank pages with zero usable embedded output must fall
back to `full_visual_ocr` (or typed failure). Dense forms whose candidate
boxes omit substantial visible ink fail a generic coverage gate and route to
full OCR. Source labels are exact and state-keyed. Phase 3 provisional policy
is retained for diagnostics; Phase 4 reconciled policy derives from final page
authorities. Document `not_required` is reserved for all-digital-native
retention with no visual stage work.

## Consequences

Empty embedded authority is impossible at the contract layer. Overlay boxes
for verified embedded OCR come from materialised public words/lines. Sparse
background OCR layers on populated forms no longer claim authority.
