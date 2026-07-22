# ADR 0017 — pypdfium2 page rendering

## Status

Accepted (Phase 4)

## Context

Phase 4 needs page rasters for visibility probes and printed OCR. Phase 3 used
`pdfplumber` for native text only and did not render pages.

## Decision

Use **pypdfium2 5.12.1** as the direct page renderer under
`backend/app/extraction/visual/renderer.py`. Render **one page at a time**,
never keep a full-document raster array. Default OCR render DPI is **200**;
visibility probes use a lower DPI (default 96). Coordinates remain normalised
page space, origin top-left, values in `[0, 1]`.

## Consequences

`pypdfium2` is promoted from a pdfplumber transitive dependency to a direct
runtime dependency (Apache-2.0 / BSD-3-Clause). Application code must not import
OpenCV for rendering.
