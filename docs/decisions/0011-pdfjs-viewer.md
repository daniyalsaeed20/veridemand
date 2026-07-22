# ADR 0011 - PDF.js viewer

- Status: Accepted
- Date: 2026-07-22
- Phase: 2

## Context

Phase 2 must display canonical PDFs in the browser with scale controls and
synthetic overlay alignment proof, without server-side rendering to images.

## Decision

- Use **`pdfjs-dist` 6.1.200** in the frontend to render canonical PDFs fetched
  from `GET .../canonical` (same-origin via the dev proxy / API base URL).
- Worker initialisation follows PDF.js ESM guidance; the viewer lives under
  `frontend/src/features/viewer/`.
- Scale min/max/step mirror backend `Settings` defaults (also exposed as frontend
  constants) so UI limits stay consistent with the specification.
- Overlays draw from `GET .../canonical/overlay-proof` using normalised geometry
  mapped into the canvas coordinate system; overlays are labelled **synthetic**.
- Byte-range requests (`Range: bytes=…`) are supported by Starlette `FileResponse`
  for efficient reloads; the viewer may rely on full fetch initially.

## Consequences

- No MuPDF/pdfium server render in Phase 2; PDF.js bundle size is accepted for
  in-browser viewing.
- Overlay accuracy is validated against synthetic proof geometry, not OCR output.
- PDF.js upgrades require licence review and a viewer regression pass.
