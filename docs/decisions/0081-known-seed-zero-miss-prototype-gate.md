# ADR 0081 — Known-seed zero-miss prototype gate

## Status

Accepted (Phase 5 Task C1)

**Gate failed** (`DETECTOR COVERAGE STILL INSUFFICIENT`). Do not weaken.
Corpus limitation (55 seeds / 9 pages) remains explicit — not universal recall.

## Context

Universal handwriting recall cannot be proven from 55 project seeds. Weakening
the gate to “best Hmean” would hide misses the classifier can never see.

## Decision

A detector configuration is eligible for the next retraining task only when it
detects **all** 55 known seeds across overall and style slices (digits,
hand-print, cursive, signatures, longer notes), with no pathological
full-page boxes and recognition compatibility not `not_acceptable`.

If none pass: report Pareto candidates and miss-slice aggregates; do not
retrain; do not weaken the gate.

## Consequences

Passing the gate means only
`HANDWRITING-CAPABLE DETECTOR CANDIDATE READY` (shadow candidate + optional
corpus v2). Failing means `DETECTOR COVERAGE STILL INSUFFICIENT`.
