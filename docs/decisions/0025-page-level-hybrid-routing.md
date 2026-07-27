# 0025 — Page-level hybrid routing

## Status

Accepted

## Context

Phase 4 sent many image-dominant pages to full Paddle OCR even when a usable
embedded text layer existed. Document-level visual escalation could suppress
good pages.

## Decision

Introduce a deterministic page router (`backend/app/extraction/routing/`) that
selects digital native, embedded OCR verified, targeted repair, full OCR, or
visual_no_text per page. Document escalation warnings remain, but Phase 4.5
positive verification may retain page-level trusted evidence.

## Consequences

Unnecessary full OCR is reduced without weakening the Phase 3 trust threshold
(0.75 unchanged).
