// PDF.js bootstrap (Phase 2).
//
// The worker script is bundled locally via Vite's `?url` import so the built
// app never depends on a CDN (mozilla's default `unpkg`/`cdnjs` worker URLs are
// explicitly not used here). Import this module (or `pdfjsLib`) before calling
// `getDocument` anywhere in the viewer feature.

import { GlobalWorkerOptions, getDocument, version } from "pdfjs-dist";
// `?url` resolves to a same-origin, build-time-hashed asset URL — never a
// network fetch to a third-party CDN.
import pdfWorkerSrc from "pdfjs-dist/build/pdf.worker.min.mjs?url";

export type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  PDFPageProxy,
  PageViewport,
  RenderTask,
} from "pdfjs-dist";

GlobalWorkerOptions.workerSrc = pdfWorkerSrc;

// Exposed for tests and diagnostics; never read from a remote origin.
export const PDFJS_WORKER_SRC = pdfWorkerSrc;
export const PDFJS_VERSION = version;

export { getDocument };
