# ADR 0061 — Project-only evaluation with public training supplementation

## Status

Accepted (Phase 5 Task B2)

**Failed baseline — superseded for the current release path** (later B3/B4 eras also failed; release architecture is ADRs 0082–0087). No `production_candidate` classifier shipped.

## Context

Public handwriting improves training coverage but must not redefine VeriDemand
product safety claims. Task B established leave-one-source-group-out (LOSGO)
diagnostics on private project crops as the prototype gate.

## Decision

1. Public Handwritten ASAP samples may appear in **every LOSGO train fold** and
   in the final fit, alongside project fit labels and synthetic non-text.
2. Held-out folds contain **only** project source-group crops.
3. Threshold search, safety gates, FP/FN aggregates, printed retention, and
   handwriting safe-bypass metrics use **project OOF predictions only**.
4. Optional public-domain diagnostics, if ever reported, must be labelled
   `public training-domain diagnostic only` and never replace project gates.
5. Do not count oversampled project handwriting exposures as additional
   human-labelled examples.

## Consequences

- Comparability with Task B baselines is preserved.
- Public subset manifests remain gitignored and must not reference private
  crop IDs or paths.

## Related

- ADR 0056 (source-group-isolated diagnostics)
- ADR 0059 (ASAP supplementation)
