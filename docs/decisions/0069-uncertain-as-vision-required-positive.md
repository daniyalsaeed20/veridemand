# ADR 0069 — Uncertain as positive vision_required training target

## Status

Accepted (Phase 5 Task B4)

## Context

Under Tasks B–B3 the 54 human-confirmed uncertain project crops were
challenge-only. They never supervised the primary head, so the model was not
trained to reserve them from Paddle.

## Decision

Treat uncertain as a training positive for `vision_required` (target = 1).
Mask the `handwriting_present` loss completely for uncertain examples so they
are not forced into handwritten or non-text. Public ASAP handwriting and
synthetic non-text remain training-only; all safety gates stay project OOF.

## Consequences

Uncertain crops enter LOSGO fit/held-out with their source groups. Challenge
manifests become empty under B4. Handwriting-head masking must be deterministic
and numerically stable when a batch is fully masked.
