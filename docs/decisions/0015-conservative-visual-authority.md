# ADR 0015 — Conservative visual authority

## Status

Accepted (Phase 3)

## Context

SoT eventually requires visual-page agreement. Phase 3 lacks a backend renderer.

## Decision

When native-only evidence cannot prove trustworthiness — including image-dominant
pages with a hidden text layer — choose `visual_authority` (or `image_authority`
for image-origin pages). Whole-document escalation suppresses previously accepted
text when failure ratio thresholds are met.

## Consequences

Some false rejections are expected until Phase 4 adds rendered-page evidence.
Rejected text remains fully suppressed.
