# ADR 0082 — Image-dominant conservative page reservation

## Status

Accepted (Phase 5 Task C3)

## Context

Task C2 showed that reserving pages when `page_is_image_dominant` is true covers
all 55 confirmed handwriting seeds and all 7 remaining Task C1 detector misses.
Region-level routers remain unsafe (Tasks B–B4).

## Decision

When `HANDWRITING_PAGE_VISION_FALLBACK_ENABLED=true` and mode is `conservative`,
image-dominant pages are reserved for Phase 6 using the existing Phase 4
predicate `page_is_image_dominant`. Local Paddle recognition is prohibited on
those pages. The feature defaults to **off**.

## Consequences

- About half of the private corpus pages lose local OCR while reserved.
- Phase 4 behaviour is unchanged when the flag is off.
- No vision-provider call occurs in Phase 5.
