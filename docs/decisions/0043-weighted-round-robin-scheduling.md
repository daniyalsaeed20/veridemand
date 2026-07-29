# 0043 — Weighted round-robin scheduling

## Status

Accepted

## Context

A scheduling policy must balance fairness across documents of different sizes
without random selection or unpredictable behaviour.

## Decision

Use weighted round-robin with three priority classes (interactive_short, normal,
large_background) determined by heavy page count. Within each class, FIFO
admission order applies. No random selection.

## Consequences

Scheduling order is deterministic and reproducible. Small documents consistently
receive earlier turns. Priority classification is based on measurable workload,
not filenames or document type labels.
