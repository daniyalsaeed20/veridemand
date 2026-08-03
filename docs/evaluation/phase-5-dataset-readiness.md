# Phase 5 dataset readiness

**Status:** PRIVATE CORPUS POPULATED — PROTOTYPE LABELLING PATH OPEN (ADR 0053)

Generated (UTC): `2026-07-31T06:45:38.674612+00:00`

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
- Full queue authorised for review: **False**
- Pilot crop count: **600**
- Pilot version: `phase5-annotation-pilot-v1`
- Pilot SHA-256: `b35d89c2022eadfbccf058b86a9cbea64efea1f6e13ebb64033fedb412a225e5`
- Manual-region worklist pages: **0**
- Manual-region requirement: **not_yet_human_verified**
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
- Release dual-agree `training_eligible` remains dual-review gated; prototype
  single-pass labels use separate `prototype_model_eligible` (ADR 0053).
- Default Task A human review uses `prototype-primary`.
- Dual pilot and full primary queue remain available but parked for hardening.
- Outstanding coverage corrections (10 pages) are parked; excluded from the
  prototype queue sample.
- Manual-region requirement: not yet human-verified (release hardening).
- Splits / held-out freeze are not generated for the prototype path alone.
- Private crops, paths, and transcripts are never committed.

See `docs/datasets/phase-5-handwriting-dataset.md`,
`docs/evaluation/phase-5-annotation-pilot.md`,
`docs/operations/phase-5-labelling.md`, ADR 0052, and ADR 0053.
