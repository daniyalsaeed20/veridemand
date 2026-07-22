# ADR 0014 — Native trust policy

## Status

Accepted (Phase 3)

## Context

A native text layer must never be trusted merely because it exists.

## Decision

Ship policy version `phase3-v1` with provisional thresholds (trust 0.75, failure
ratio 0.30) and component weights summing to 1. Hard rejection overrides the
weighted score. Visual agreement is **not evaluated** in Phase 3
(`visual_agreement_status=not_evaluated_phase_3`, score `null`).

## Consequences

Calibration against synthetic and private corpora may revise thresholds with
documented evidence. No filename/hash/value exceptions.
