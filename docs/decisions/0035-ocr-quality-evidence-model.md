# ADR 0035 — Printed OCR quality-evidence model

## Status

Accepted (Correction 5)

## Context

Operators and UI need a single explanation for quality and fallback decisions.
Computing one decision in the backend and a different narrative in the frontend
causes drift. Mean confidence is often mistaken for accuracy.

## Decision

`PrintedOcrQualityEvidence` is the sole typed evidence model for:

- primary-pass acceptance;
- fallback recommendation reason codes;
- quality status (`good` / `usable_with_warnings` / `low_quality` / `insufficient` / `failed`);
- development quality panels.

Every metric documents whether higher is better or worse. Confidence aggregates
are never labelled as accuracy.

## Consequences

- UI and logs must derive displays from this model (or fields copied from it).
- Policy version `phase4-ocr-quality-v1` is recorded on results.
