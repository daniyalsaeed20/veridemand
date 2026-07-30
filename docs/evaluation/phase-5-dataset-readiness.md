# Phase 5 dataset readiness

**Status:** DATASET TOOLING READY — HUMAN LABELLING REQUIRED

Generated (UTC): `2026-07-31T00:00:00+00:00` (tooling bootstrap; refresh with `pnpm phase5:dataset:report`)

## Aggregate counts (opaque)

- Crops in private manifest: **0**
- Review events: **0**
- Resolved records: **0**
- Training-eligible (agreed/adjudicated 3-class): **0**
- Split manifest present: **False**
- Held-out frozen: **False**

### Resolution status

- _(none — human labelling not started)_

### Human labels

- _(none — expect zeros until private labelling)_

## Policy

- Labels are human-only (`printed` / `handwritten` / `uncertain` / `non_text`).
- Signatures are labelled `handwritten`.
- `uncertain` is excluded from initial 3-class training.
- Splits are group-aware (`source_group_id` + `duplicate_family_id`).
- Private crops, paths, and transcripts are never committed.

See `docs/datasets/phase-5-handwriting-dataset.md` and ADR 0051.
