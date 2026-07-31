# Phase 5 dataset readiness

**Status:** DATASET TOOLING READY — PRIMARY HUMAN REVIEW PENDING

Generated (UTC): `2026-07-31T00:54:56.379665+00:00`

## Aggregate counts (opaque)

- Schema version: `phase5-dataset-schema-v1`
- Crop padding version: `phase5-crop-pad-v1`
- Documents registered: **6**
- Source groups: **6**
- Crops in private manifest: **65649**
- Unreviewed crops: **65649**
- Review events: **0**
- Resolved records: **0**
- Training-eligible (3-class agreed/adjudicated): **0**
- Primary queue crops: **44951**
- Queue version: `phase5-primary-review-queue-v1`
- Queue seed: `42`
- Queue SHA-256: `096424d0edfc49dddd07fe8dbba6fafc1e14bbe9a4860230caa0d16eebea84df`
- Manual-region worklist pages: **0**
- Split manifest present: **False**
- Held-out frozen: **False**
- Classifier training authorised: **False**

### Candidate-source coverage

- `full_page_ocr`: 65649

### Broad source-family coverage

- `billing_ledger`: 2
- `other`: 4

### Resolution status

- _(none — primary human review pending)_

### Human labels

- _(none — expect zeros until private labelling)_

## Policy

- Labels are human-only (`printed` / `handwritten` / `uncertain` / `non_text`).
- Signatures are labelled `handwritten`.
- `uncertain` is excluded from initial 3-class training.
- No classifier training is authorised yet.
- Splits are not generated until labels exist.
- Private crops, paths, and transcripts are never committed.

See `docs/datasets/phase-5-handwriting-dataset.md` and ADR 0051.
