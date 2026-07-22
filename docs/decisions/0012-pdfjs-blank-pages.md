# ADR 0012 - PDF.js range CORS, WASM codecs, and render lifecycle

- Status: Accepted
- Date: 2026-07-22
- Phase: 2 (blank-page remediation)

## Context

Manual corpus testing found blank white pages in the PDF.js viewer while page
counts remained correct. Investigation against four private medical PDFs showed:

1. Canonical PDFs were **byte-identical** to originals; Chrome/desktop viewers
   were fine. The defect was in-browser PDF.js rendering.
2. Console: `Ensure that the wasmUrl API parameter is provided` and
   `Jbig2Error: JBig2 failed to initialize` — scanned pages use JBIG2/CCITT
   image XObjects and need `pdfjs-dist/wasm/` codecs.
3. Isolation mode (full-file load) did **not** fix blanks.
4. Separately, CORS only exposed `X-Request-ID`, so PDF.js could not read
   `Accept-Ranges` / `Content-Range` / `Content-Length` cross-origin; and
   `PdfCanvas` cancelled `RenderTask`s without awaiting them before resizing
   the canvas (clearing pixels).

## Decision

1. Pass `wasmUrl` (trailing slash) to `getDocument`, serving unhashed files from
   `/pdfjs-wasm/` (Vite syncs `pdfjs-dist/wasm` into `public/pdfjs-wasm/`).
2. Expose `Accept-Ranges`, `Content-Range`, `Content-Length`, and `Content-Type`
   via CORS `expose_headers`.
3. Harden the render lifecycle: one active task per canvas, cancel-and-await
   before reuse, monotonic generation tokens, no canvas clear from stale
   cleanup, render-completion state, blank-canvas detection, and diagnosed
   error + Retry UI.
4. Keep range loading **enabled**. `VITE_PDFJS_ISOLATION_MODE` is diagnostic-only.
5. Hide the synthetic alignment overlay unless `DEV` and
   `VITE_SHOW_ALIGNMENT_OVERLAY=true`.

## Consequences

- JBIG2/JPEG2000 medical pages paint correctly when WASM is reachable.
- Large PDFs can stream via ranges without opaque CORS headers.
- Rapid page/zoom/rotation churn no longer leaves silent blank canvases.
- WASM codec licences shipped with pdfjs-dist (`LICENSE_*` under `wasm/`) apply
  to the copied `/pdfjs-wasm/` assets; they are not new product dependencies.
