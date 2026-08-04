# ADR 0067 — Asymmetric prototype safety gates (dual-risk)

## Status

Accepted (Phase 5 Task B3)

## Context

Task B ADR 0057 and Task B2 ADR 0062 defined aggregate and slice gates for the
three-class baseline. Dual-risk adds an explicit handwritten→non_text discard
failure that must also be zero, because non_text is not a safe bypass for
human-confirmed handwriting.

## Decision

A dual-risk candidate passes prototype engineering gates only when all project
out-of-fold conditions hold:

1. handwritten → printed count = 0
2. handwritten → non_text count = 0
3. handwriting safe-bypass recall = 100% (`handwritten` ∨ `uncertain` only)
4. cursive → printed or non_text count = 0
5. signature → printed or non_text count = 0
6. non_text → printed count = 0
7. printed retention recall ≥ 80%

Lexicographic threshold search follows Task B3 §14.1. Do not weaken gates.
Do not use public or synthetic samples to select final routing thresholds.
Do not claim release held-out evaluation — diagnostics remain
source-group-isolated out-of-fold prototype diagnostics.

## Consequences

Only a package that clears every gate may be marked `production_candidate`.
Otherwise the decision token is `SAFETY-FIRST MODEL STILL NOT SAFE`. Router
defaults remain disabled.
