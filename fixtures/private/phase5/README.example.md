# Private Phase 5 handwriting crop dataset (not committed)

This directory holds **local-only** Phase 5 region crops, manifests, and review
records. Everything under `fixtures/private/phase5/` is git-ignored except this
example README. **Never commit crops, page images, private manifests, review
events, or source documents.**

## Expected layout (create with `pnpm phase5:crops:init`)

```text
fixtures/private/phase5/
├── sources/           # private source files (optional copies)
├── pages/             # private page renders (gitignored)
├── crops/             # opaque crop images (gitignored)
├── manifests/
│   ├── source-manifest.jsonl
│   ├── crop-manifest.jsonl
│   ├── review-events.jsonl
│   ├── resolved-labels.jsonl
│   ├── exclusions.jsonl
│   └── split-manifest.jsonl
├── reports/           # private readiness reports
├── locks/
└── backups/
```

## Commands

See `docs/datasets/phase-5-handwriting-dataset.md` and
`docs/operations/phase-5-labelling.md`.

Human labels are never derived from OCR text or classifier predictions.
