# 0030 — Fair document scheduling

## Status

Accepted

## Context

A long full-OCR document can block later short documents indefinitely under
FIFO page processing.

## Decision

Optional fair OCR scheduling (`FAIR_OCR_SCHEDULING_ENABLED`) processes bounded
page work, checkpoints, and yields between documents without reloading models.

**Correction 7 update:** the chunk-size setting `FAIR_OCR_PAGE_CHUNK_SIZE` is
replaced by `FAIR_OCR_PAGE_QUANTUM` / `FAIR_REPAIR_PAGE_QUANTUM`. Existing
`.env` values of `FAIR_OCR_PAGE_CHUNK_SIZE` are migrated with a deprecation
warning. Default enablement for the Correction 7 branch is `true`; disable to
retain Correction 6 FIFO. See ADRs 0042–0046 and
`docs/architecture/phase-4-fair-scheduling.md` for the locked interim overlay.

## Consequences

Total OCR work is unchanged; latency fairness for short documents improves when
enabled.
