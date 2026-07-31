# Phase 5 labelling operations

## Default workflow (Task 3C) — annotation pilot first

Do **not** start full-corpus labelling until the pilot is reviewed and approved
(ADR 0052).

### 0. Backup private manifests

```bash
pnpm phase5:dataset:backup
```

### 1. Page-level coverage review (separate from script labels)

```bash
pnpm phase5:dataset:backup
pnpm phase5:coverage:build
pnpm phase5:coverage:verify
pnpm phase5:coverage:serve -- --reviewer cov_reviewer_01
```

Open `http://127.0.0.1:8766/?reviewer=cov_reviewer_01` (opaque coverage
reviewer id; not a personal name).

Coverage outcomes are **not** script labels. After human completion:

```bash
pnpm phase5:dataset:backup
pnpm phase5:coverage:verify -- --events
pnpm phase5:coverage:worklist
pnpm phase5:coverage:report -- --write-aggregate docs/evaluation/phase-5-coverage-review.md
```

Manual-region status remains `not yet human-verified` until humans finish
coverage review. Do not open crop labelling until coverage is accepted or
corrections are complete.

### 2. Primary pilot (600 crops)

```bash
pnpm phase5:labels:serve -- --queue pilot-primary --reviewer rev_<opaque_id>
```

URL shape:

```text
http://127.0.0.1:8765/?role=primary&queue=pilot-primary&reviewer=rev_<opaque_id>
```

### 3. Secondary pilot (different reviewer)

```bash
pnpm phase5:labels:serve -- --queue pilot-secondary --reviewer rev_<different_opaque_id>
```

The same `reviewer_id` **must not** serve both pilot primary and secondary roles.

### 4. Agreement / conflicts (after both reviews exist)

```bash
pnpm phase5:labels:pilot-report
pnpm phase5:labels:adjudication
pnpm phase5:labels:resolve
pnpm phase5:dataset:report
```

### 5. Stop before full-corpus review

The full primary queue (~45k canonical crops) remains preserved and marked:

```text
full primary queue — not authorised for review until pilot approval
```

Serving it requires an explicit flag:

```bash
pnpm phase5:labels:serve -- --queue full-primary --authorise-full-queue --reviewer rev_<opaque_id>
```

Do not authorise training, splits, or held-out freeze from the pilot alone.

## Blind review rules

- UI shows the crop image and opaque `crop_id` only.
- No OCR text, confidence, filenames, case names, source paths, candidate
  provenance, or sampling reasons.
- Secondary does not see primary labels/notes/progress.
- Events are append-only JSONL with crop SHA-256.
- No `localStorage` / browser persistence of private payloads.
- Quality flags (`crop_too_tight`, `requires_page_context`, …) do **not**
  auto-change the label.
- `requires_page_context` records that the blind crop was insufficient and
  routes to a separate context-review worklist — do not force a label.

## Label definitions

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

## Full-corpus queue (not default)

```bash
pnpm phase5:labels:queue -- --seed 42
```

Rebuilds the full primary queue only. It is **not** the default human task.

## Related docs

- `docs/evaluation/phase-5-annotation-pilot.md`
- `docs/evaluation/phase-5-source-group-adequacy.md`
- `docs/evaluation/phase-5-dataset-readiness.md`
- ADR 0051, ADR 0052
