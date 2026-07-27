# 0027 — Targeted region repair

## Status

Accepted

## Context

Limited local failures should not force whole-page OCR.

## Decision

Cluster failed boxes into a bounded number of padded regions, repair locally,
and escalate to full OCR when region count or coverage exceeds policy limits.

## Consequences

Accepted embedded text outside failed regions is preserved.
