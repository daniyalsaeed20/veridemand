# ADR 0052 — Phase 5 annotation pilot and coverage gate

## Status

Accepted (Phase 5 Task 3C)

## Context

Task 3B populated a private crop corpus (~65k records / ~45k canonical) and a
full primary review queue. Full-corpus labelling before guideline validation
risks inconsistent labels, unreviewed page coverage gaps, and group-level
overfitting from only six source groups. Candidate provenance must remain
selection metadata, never a script label.

## Decision

1. **Pilot before full review.** Human crop labelling defaults to a
   deterministic 600-crop annotation pilot (`phase5-annotation-pilot-v1`,
   sampling policy `phase5-annotation-pilot-sampling-v1`). The full primary
   queue is preserved but marked
   `full primary queue — not authorised for review until pilot approval` and
   requires an explicit `--authorise-full-queue` flag.
2. **Dual blinded pilot review.** Independent queues `phase5-pilot-primary-v1`
   (seed 3101) and `phase5-pilot-secondary-v1` (seed 3102) share membership with
   materially different order. The same opaque reviewer ID must not serve both
   pilot roles. Secondary does not see primary labels, notes, progress,
   candidate provenance, or sampling reasons.
3. **Page-level coverage verification.** A separate loopback coverage-review
   workflow audits page overlays and skipped-block gaps. Coverage outcomes are
   not script labels. Manual-region conclusions remain
   `not yet human-verified` until humans complete coverage review.
4. **Source-group limitation.** With only six independent source groups,
   release held-out freezing is prohibited unless an explicit later project
   decision records provisional acceptance. Adequacy status is
   `SOURCE-GROUP COVERAGE INSUFFICIENT FOR RELEASE EVALUATION`.
5. **No fabricated labels.** Cursor/agents do not assign private human labels,
   invent coverage events, train models, export ONNX, or modify live OCR routing
   in Task 3C.

## Consequences

Operators run `pilot-primary` / `pilot-secondary` first. Pilot agreement and
guideline quality inform whether full-corpus review may begin. Training, splits,
and held-out freeze remain blocked. Private overlays, pilot manifests, and
queues stay gitignored.
