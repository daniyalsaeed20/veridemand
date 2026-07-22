# Phase 2 — PDF.js blank pages investigation

- Date: 2026-07-22
- Branch: `fix/phase-2-pdfjs-blank-pages`
- Base tag: `phase-2-canonical-viewer-coordinates-v1` (`c44dc5af683c17f4fa00660fe1e883a5244ddd2e`)

Private PDFs were used from gitignored `fixtures/private/` only. No PHI content
and no private filenames are recorded here.

## Corpus (original PDF → canonical)

Four local private medical-record PDFs (67, 104, 52, and 53 pages) were
uploaded through the Phase 2 canonical path. For each file:

- Canonicalisation method: `original_pdf`
- Original bytes SHA-256 matched the downloaded canonical bytes (byte-identical)
- Range probe `bytes=0-63` returned **206** with correct `Content-Range`,
  `Content-Length`, and body bytes

Chrome’s built-in viewer and desktop PDF viewers therefore see the same
bitstreams as the source files (verified by hash identity + `%PDF` integrity).

## Affected pages (before fix)

With PDF.js **without** `wasmUrl`, Chromium render probes showed **entire
sampled pages blank** (dark/ink pixel count ≈ 0) across the four private
files (first/last/mid pages sampled). Isolation mode (`disableRange` /
`disableStream` / `disableAutoFetch`) **did not** fix blanks. Range/CORS was
a secondary hardening item, not the primary cause for this corpus.

## Console evidence (before fix)

```text
Warning: #instantiateWasm: UnknownErrorException: Ensure that the `wasmUrl` API parameter is provided.
Warning: #getJsModule: TypeError: Failed to resolve module specifier 'nulljbig2_nowasm_fallback.js'
Warning: Unable to decode image "img_p0_1": "Jbig2Error: JBig2 failed to initialize".
Warning: Dependent image isn't ready yet
```

Page resources are image XObjects (CCITT / JBIG2 / DCT). PDF.js 6 needs the
packaged WASM codecs under `pdfjs-dist/wasm/`.

## After fix

Configured `getDocument({ wasmUrl: "/pdfjs-wasm/" })` and sync
`pdfjs-dist/wasm` → `frontend/public/pdfjs-wasm/` via Vite. Full-page re-probe
of all four private files:

- `blankWithRange: []` and `blankIsolation: []` for every page
- No JBIG2 initialize errors

Also hardened: CORS `expose_headers` for range headers, RenderTask
cancel-and-await + generation tokens, blank-canvas → explicit error + Retry,
overlay off by default.

## Decision

Keep range loading enabled. Isolation mode remains diagnostic-only. Do not
disable WASM.
