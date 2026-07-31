# Phase 5 labelling operations

## Private primary-review workflow (Task 3B)

After crop export and queue generation (gitignored under `fixtures/private/phase5/`):

1. Verify crop integrity:

```bash
pnpm phase5:crops:verify
```

2. Confirm the primary queue exists (opaque aggregates only):

```bash
pnpm phase5:labels:queue -- --seed 42
```

3. Backup manifests before labelling:

```bash
pnpm phase5:dataset:backup
```

4. Start the loopback labeler:

```bash
pnpm phase5:labels:serve
```

5. Open the primary-review URL with an opaque reviewer ID:

```text
http://127.0.0.1:8765/?role=primary&reviewer=rev_<your_opaque_id>
```

Also available: `role=secondary`, `role=adjudicator`.

The server binds **loopback only**. It is not part of the production API or
frontend bundle. Do not expose it on LAN/WAN.

### Blind review rules

- UI shows the crop image and opaque `crop_id` only.
- No OCR text, confidence, filenames, case names, or source paths.
- Secondary reviewers do not see the primary label (except adjudicators on conflicts).
- Events are append-only JSONL with the crop SHA-256.
- No `localStorage` / browser persistence of private payloads.
- Do not paste visible OCR text into notes.
- Do not inspect OCR predictions or classifier scores while labelling.

### Label definitions

| Label | Meaning |
|-------|---------|
| printed | Machine-printed text style |
| handwritten | Handwriting style (including signatures) |
| uncertain | Ambiguous / vision-reserved; not training-eligible |
| non_text | Borders, noise, logos, non-text marks |

### Signature and uncertain policy

- Signatures → `handwritten` (keyboard `S`).
- Use `uncertain` only when style cannot be decided.
- Use `X` (exclude) for corrupt/unusable crops — not as a substitute for `uncertain`.

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

### Progress, resume, backup, mistakes

- Progress is saved as append-only `review-events.jsonl` under the private root.
- Stop the labeler with Ctrl+C; resume later with the same serve command — the queue skips already labelled crops after `phase5:labels:queue` regeneration if needed.
- Back up before and after sessions: `pnpm phase5:dataset:backup`.
- Mistakes: append a corrected label / exclude event (append-only; do not edit history by hand).
- After a session: `pnpm phase5:labels:resolve` then `pnpm phase5:dataset:report`.

### Review-progress report

```bash
pnpm phase5:dataset:report
```

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
