# Phase 5 — Page-level vision reservation (architecture)

**Status:** Phase 5 in progress — conservative full-page vision reservation
implemented for image-dominant pages; Phase 6 provider processing is not yet
implemented.

## Behaviour

```text
native page available
  → page_is_image_dominant (existing Phase 4 predicate)
  → HANDWRITING_PAGE_VISION_FALLBACK_ENABLED?
       no  → Phase 4 hybrid path unchanged
       yes + dominant + mode=conservative
            → skip probe / router / Paddle / repair / classifier
            → publish vision_reserved_pending_phase_6
            → document may become awaiting_phase_6
```

## Contracts

- `PageVisionReservationEvidence` — required/status/reason/scope/policy/bbox/render
- Exclusive route: `vision_reserved_pending_phase_6`
- Document lifecycle: `awaiting_phase_6`
- Full-page geometry: normalised `[0,0,1,1]` (top-left)
- No provider name, credentials, transcription, or fabricated region crops

## Settings

| Env | Default |
|-----|---------|
| `HANDWRITING_PAGE_VISION_FALLBACK_ENABLED` | `false` |
| `HANDWRITING_PAGE_VISION_FALLBACK_MODE` | `conservative` (only accepted value) |

## Authority

Provisional native/embedded evidence may remain on the page diagnostics, but
reserved pages never claim native or embedded final authority and never publish
final extracted text.

## Related ADRs

0082–0087.
