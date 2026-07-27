# 0030 — Fair document scheduling

## Status

Accepted

## Context

A long full-OCR document can block later short documents indefinitely under
FIFO page processing.

## Decision

Optional fair OCR scheduling (`FAIR_OCR_SCHEDULING_ENABLED`, default false)
processes bounded page chunks, checkpoints, and yields between documents
without reloading models. Enable only after benchmark evidence.

## Consequences

Total OCR work is unchanged; latency fairness for short documents improves when
enabled.
