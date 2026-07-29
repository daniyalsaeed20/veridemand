# 0027 — Targeted region repair

## Status

Superseded by Correction 6 ADRs 0038–0041

## Context

Limited local failures should not force whole-page OCR.

## Decision

Cluster failed boxes into a bounded number of padded regions, repair locally,
and escalate to full OCR when region count or coverage exceeds policy limits.

Correction 6 implements the full eligibility evidence model, recognition-only
and local-detection methods, retained/repaired reconciliation, quality gate,
atomic publication, and cleanup. See:

- `0038-targeted-repair-eligibility.md`
- `0039-repair-method-selection.md`
- `0040-repair-result-reconciliation.md`
- `0041-repair-to-full-ocr-fallback.md`

## Consequences

Accepted embedded text outside failed regions is preserved.
