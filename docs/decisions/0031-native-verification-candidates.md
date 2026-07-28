# 0031 — Native verification candidates for embedded OCR

## Status

Accepted

## Context

Phase 3 strips word boxes on reject/suppress so rejected text never appears as
accepted output. Phase 4.5 embedded-OCR verification needs those boxes; without
them every image-dominant page falls through to full OCR (medical baseline:
0 embedded verified / 104 full OCR).

SoT §10.5 allows rejected native text in diagnostic metadata when clearly marked
rejected. ADR 0025 allows page-level retention for positive verification.

## Decision

Persist `verification_words` on rejected/suppressed pages that still have usable
geometry. Entries use `recognition_status=rejected`. Accepted fields
(`words`, `characters`, `provisional_native_text`) stay empty for non-accepted
pages. Phase 4.5 Route B reads `words` or else `verification_words`. Route A
(digital native) remains accepted-only. Default public API omits
`verification_words`.

Phase 3 trust threshold (0.75) and hard-reject rules are unchanged.

## Consequences

Usable embedded OCR layers can skip full OCR after visual/recognition agreement.
Ambiguous near-overprint pages with no candidates remain empty and still route
to full OCR.
