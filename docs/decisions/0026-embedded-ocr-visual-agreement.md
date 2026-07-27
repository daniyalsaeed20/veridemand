# 0026 — Embedded OCR visual agreement

## Status

Accepted

## Context

Scanned pages often contain an embedded OCR layer that Phase 3 cannot fully
validate without visual evidence.

## Decision

Add low-DPI visual agreement and optional recognition spot checks with
centralised thresholds and privacy-safe aggregate metrics only.

## Consequences

Accurate embedded layers can skip full OCR; bad layers escalate to repair or
full OCR.
