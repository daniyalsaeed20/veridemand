# ADR 0003 - Phase 0 readiness

- Status: Accepted
- Date: 2026-07-21
- Phase: 0

## Context

Readiness must reflect only capabilities that are actually active. Phase 0 has
no upload, processing, OCR, LibreOffice, model, or vision integration, so
requiring those would make a healthy foundation report "not ready".

## Decision

`GET /health/ready` checks only Phase 0 required dependencies:

1. Settings loaded and validated.
2. `TEMP_ROOT` exists or can be created, and is writable (verified by creating
   and deleting a small probe file).

Future dependencies (`libreoffice`, `paddle_ocr`, `handwriting_classifier`,
`openai_vision`) are reported as optional `not_configured` checks
(`required: false`). They are informational only and never make the service
unready.

- `200` + `status: "ready"` when all required checks pass.
- `503` + `status: "not_ready"` when any required check fails.

## Consequences

- Later phases will promote the optional checks to real, required checks as the
  corresponding capabilities become active, extending `HealthService` without
  changing the response contract shape.
