# ADR 0073 — Retain all detector regions before recognition

## Status

Accepted (Phase 5 Task C0)

## Context

The post-recognition crop corpus dropped regions that produced no text. Those
regions are exactly the ones a handwriting / uncertain router may need.

## Decision

The detector-first manifest retains every valid detection regardless of
recognition outcome. Recognition status is metadata
(`not_run` / `recognised` / `empty` / `low_confidence` / `failed` / `rejected`).

Committed reports never include OCR text.

## Consequences

Classifier training pools can include empty-recognition detector crops.
Corpus size increases versus the legacy combined export.
