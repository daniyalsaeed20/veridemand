# Phase 5 — Page vision reservation acceptance (Task C3)

## Decision

```text
PAGE-LEVEL VISION RESERVATION ACCEPTANCE PASSED
```

Conservative fallback reuses `page_is_image_dominant` and matches Task C2
coverage gates on the private corpus.

## Safe aggregates

| Aggregate | Value |
|-----------|------:|
| Pages | 215 |
| Reserved | 107 |
| Non-reserved | 108 |
| Reservation rate | 49.8% |
| Documents / source groups affected | 3 / 3 |
| Known handwriting pages reserved | 9 / 9 |
| Confirmed handwriting seeds covered | 55 / 55 |
| Task C1 miss seeds covered | 7 / 7 |
| Paddle recognition calls on reserved pages | 0 |
| Vision-provider calls | 0 |
| Reserved pages marked fully complete | 0 |
| Overall progress maximum | 65% |

Non-reserved source-family histogram (aggregates):

| Family | Pages |
|--------|------:|
| other | 97 |
| billing_ledger | 10 |
| image_document | 1 |

## Runtime confirmation

- Feature default remains **off**
- Acceptance profile: enabled + `conservative`
- Insertion point: visual heavy-selection loop before probe/router/Paddle
- Exclusive route: `vision_reserved_pending_phase_6`
- Document lifecycle when reserved pages exist: `awaiting_phase_6`
- Full-page geometry: `[0,0,1,1]`
- Session artefact cleanup: existing session TTL/cancel paths

## Feature-off non-regression

With the flag disabled, image-dominant pages continue through the Phase 4 hybrid
path (no reservation). Unit tests cover feature-off selection and exclusive
histogram accounting.

## Privacy

- No private IDs, filenames, OCR text, screenshots, or page images in this report
- Acceptance aggregate JSON stays under gitignored `temp/`
- No OpenAI / vision-provider network call

## Method

```text
uv run python scripts/phase5/page_vision_reservation_acceptance.py
```
