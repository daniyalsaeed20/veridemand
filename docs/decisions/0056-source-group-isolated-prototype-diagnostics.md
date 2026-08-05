# ADR 0056 — Source-group-isolated prototype diagnostics

## Status

Accepted (Phase 5 Task B)

**Failed baseline — superseded for the current release path** (later B3/B4 eras also failed; release architecture is ADRs 0082–0087). No `production_candidate` classifier shipped.

## Context

Project crops share document/source correlation. Random crop splits would leak
near-duplicates and overstate prototype quality. Only six independent source
groups exist, which is insufficient for a release held-out claim but usable for
prototype diagnostics.

## Decision

1. Evaluate candidates with **leave-one-source-group-out (LOSGO)** across all
   project source groups.
2. Fit augmentation and class weights from each training fold only.
3. Never use the outer held-out group for early stopping, LR selection,
   augmentation selection, or model selection during that fold.
4. With few remaining groups, use a fixed epoch budget rather than leaking the
   outer fold via inner validation.
5. Report metrics as **source-group-isolated out-of-fold prototype diagnostics**,
   not as final release held-out metrics.
6. Package `validation_manifest_sha256` records the OOF evaluation index used for
   threshold selection; `held_out_manifest_sha256` records a deferred-release
   placeholder (`held_out_authorised=false`) until a freeze is authorised.

## Consequences

- Some folds may lack a class; support is reported truthfully per fold.
- Final fitted model has no independent release held-out evaluation in Task B.
- Six-group limitation remains a release-hardening concern for later tasks.

## Related

- ADR 0051, ADR 0053
- `docs/evaluation/phase-5-source-group-adequacy.md`
