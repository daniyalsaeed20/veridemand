# ADR 0020 — Native visibility probe

## Status

Accepted (Phase 4)

## Context

Phase 3 could not detect white-on-white or render-mode-invisible native text.
Accepting such layers would publish untrustworthy text.

## Decision

For accepted native pages, render a low-DPI page and probe each word region with
Pillow/NumPy (variance, edge density, contrast). Outcomes:

- `native_text_visually_supported` — retain native authority.
- `native_text_not_visually_present` / `native_text_visibility_uncertain` —
  downgrade to visual authority, suppress published native text, run printed OCR.

Never log native or OCR text from the probe.

## Consequences

T18/T19-class cases become Phase 4 active expectations. Visual agreement status
becomes `evaluated_phase_4_visibility` (not a full geometric agreement score).
