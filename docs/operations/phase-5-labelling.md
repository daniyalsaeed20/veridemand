# Phase 5 labelling operations

## Loopback labeler

```bash
pnpm phase5:crops:init
pnpm phase5:labels:serve
```

Open `http://127.0.0.1:8765/?role=primary` (also `secondary`, `adjudicator`).

The server binds **loopback only**. It is not part of the production API or
frontend bundle. Do not expose it on LAN/WAN.

### Blind review rules

- UI shows the crop image and opaque `crop_id` only.
- No OCR text, confidence, filenames, case names, or source paths.
- Secondary reviewers do not see the primary label (except adjudicators on conflicts).
- Events are append-only JSONL with the crop SHA-256.
- No `localStorage` / browser persistence of private payloads.

### Keyboard

| Key | Action |
|-----|--------|
| `P` | printed |
| `H` | handwritten |
| `U` | uncertain |
| `N` | non_text |
| `S` | signature → handwritten |
| `X` | exclude |
| `Z` | skip |

## Resolve

```bash
pnpm phase5:labels:resolve
```

Resolution statuses: `unreviewed`, `single_review`, `agreed`, `conflict`,
`adjudicated`, `excluded`, `invalidated_hash_mismatch`.

Training-eligible only when status is `agreed` or `adjudicated` and the label is
one of `printed` / `handwritten` / `non_text`.

## Privacy

Never commit files under `fixtures/private/phase5/` except the allowlisted
`README.example.md`. Run `pnpm check:private` before push.
