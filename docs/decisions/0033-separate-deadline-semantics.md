# ADR 0033 — Separate deadline semantics

## Status

Accepted (Correction 4)

## Context

A single `deadline_remaining_seconds` mixed document, page, and operation
deadlines.

## Decision

Expose separate remaining fields for document/page/operation/attempt deadlines.
Null means absent. New pages reset page/operation deadlines; retries reset
attempt deadlines. Legacy single field is the most specific active deadline and
is deprecated.

## Consequences

Publication events no longer overwrite a page deadline with a document deadline
in the same field.
