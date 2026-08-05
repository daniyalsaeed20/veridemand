# ADR 0077 — Handwriting detection recall is a prerequisite for routing

## Status

Accepted (Phase 5 Task C1)

**Gate not met — insufficient for zero-miss / classifier-retrain unlock.** Release path uses ADRs 0082–0087 (page reservation), not a handwriting-capable detector candidate.

## Context

The Phase 5 writing-style classifier can only act on regions supplied by the
text detector. Task C0 measured known-seed detector recall at 0.655 (19/55
misses). Retraining the classifier cannot recover missed handwriting.

## Decision

Treat known-project handwriting detector recall as a hard prerequisite before
another classifier training run or live routing integration. Task C1 evaluates
detector candidates offline; the live Phase 4 path remains unchanged.

## Consequences

If no candidate reaches zero known-seed misses, classifier retraining is
blocked and the gap is reported explicitly. Vision-reservation fallbacks or
detector fine-tuning are deferred decisions — not automatic Task C1 work.
