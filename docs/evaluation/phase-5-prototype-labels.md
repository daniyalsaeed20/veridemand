# Phase 5 prototype labels

**Status:** PROTOTYPE LABEL SAMPLE NEEDS EXPANSION

Aggregate / opaque only. No private crop IDs, page IDs, filenames, paths,
reviewer IDs, or visible text.

## Queue

- Queue version: `phase5-prototype-primary-v1`
- Seed: `4101`
- Target size: **300**
- Actual size: **300**
- Source groups represented: **6**
- Active coverage pages excluded: **10**
- OCR confidence sampling: `unavailable_on_crop_records_skipped`
- Queue SHA-256: `e0c9a91732c4054d9cab80de72781f203e53f28671cf86738366465c21e70aaa`

### Broad family coverage (queue membership)

- `billing_ledger`: **53**
- `image_document`: **10**
- `medical_form`: **120**
- `other`: **107**
- `police_form`: **10**

## Human review (aggregate)

- Total: **300**
- Reviewed: **300**
- Remaining: **0**
- Printed: **221**
- Handwritten: **0**
- Uncertain: **54**
- Non-text: **23**
- Excluded: **2**
- Skipped: **0**
- Prototype model-eligible (3-class single-pass): **244**

### Label proportions (among labelled, non-excluded)

- `handwritten`: **0.000**
- `non_text`: **0.077**
- `printed`: **0.742**
- `uncertain`: **0.181**

### Model class project evidence

- `handwritten`: **no**
- `non_text`: **yes**
- `printed`: **yes**

## Known sampling bias

- Crops originate from combined Paddle detection/recognition evidence.
- Empty-text detections were not retained.
- Handwriting missed entirely by Paddle may be absent.
- Six source groups limit broad generalisation.
- Active coverage-issue pages were excluded from this sample (corpus gaps remain).

## Recommendation

- Enough examples for a prototype model: **no**
- Recommended next action: label more from the remaining pilot and/or supplement with licensed public/synthetic data before prototype training — at least one required model class lacks project evidence.

## Policy

- Single-pass prototype path (ADR 0053); not a release dual-review claim.
- `uncertain` retained but excluded from initial three-class fitting.
- Exclusions are distinct from `uncertain`.
- Phase 5 does not transcribe handwriting or call a vision provider.
- Release exit still requires zero handwritten/uncertain leakage into Paddle.

See ADR 0053 and `docs/operations/phase-5-labelling.md`.
