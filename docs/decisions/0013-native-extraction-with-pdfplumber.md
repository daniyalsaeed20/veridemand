# ADR 0013 — Native extraction with pdfplumber

## Status

Accepted (Phase 3)

## Context

Phase 3 must extract native PDF characters and words with coordinates from the
canonical viewer PDF without rendering or OCR.

## Decision

Use **pdfplumber** for character/word extraction and geometry. Retain **pypdf**
for structural inspection only. Do not use pdfplumber `to_image` or pypdfium2
rendering APIs.

## Consequences

- Exact versions locked via uv (`pdfplumber` 0.11.9; transitive `pdfminer.six`
  20251230; transitive `pypdfium2` 5.12.1 unused).
- Dependency-boundary guard forbids application imports of pypdfium2/OCR/LLM.
