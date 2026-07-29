# 0041 — Repair-to-full-OCR fallback

## Status

Accepted

## Context

A partial or low-quality repair must not become final page authority.

## Decision

Stage repair results and run a typed quality gate
(`repair_complete` / `repair_complete_with_warnings` / `repair_insufficient` /
`repair_failed`). On insufficient or failed: discard staging, emit one terminal
repair-insufficient signal, then run a new full-OCR operation attempt using the
Correction 5 quality gate. Do not publish the failed repair. Do not run repair
and full OCR concurrently on the same page.

## Consequences

Final authority for fallback pages is `visual_authority` / `full_visual_ocr`.
At most one bounded targeted-repair attempt per page before fallback.
