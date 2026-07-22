// PDF.js load/render configuration (Phase 2 blank-page remediation).
//
// Isolation mode and DPR caps are diagnostic levers. The default path keeps
// range + stream enabled after CORS expose_headers are fixed for cross-origin
// PDF.js clients.
//
// Medical scan PDFs often embed JBIG2 / JPEG2000 image XObjects. pdfjs-dist 6
// requires an explicit `wasmUrl` pointing at the served `public/pdfjs-wasm/`
// directory (synced from pdfjs-dist/wasm by Vite) or those pages render blank.

export type PdfRenderStatus = "idle" | "rendering" | "rendered" | "error";

export type PdfRenderDiagnosticCode =
  "PDFJS_RENDER_FAILED" | "PDFJS_INVALID_VIEWPORT" | "PDFJS_NO_CONTEXT" | "PDFJS_BLANK_PAGE" | null;

function envFlag(name: string): boolean {
  const raw = import.meta.env[name];
  if (typeof raw !== "string") {
    return false;
  }
  const normalised = raw.trim().toLowerCase();
  return normalised === "1" || normalised === "true" || normalised === "yes";
}

function envNumber(name: string): number | null {
  const raw = import.meta.env[name];
  if (typeof raw !== "string" || raw.trim() === "") {
    return null;
  }
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

/** Base URL for pdfjs-dist WASM codecs (JBIG2, OpenJPEG, qcms). Trailing slash required. */
export function getPdfjsWasmUrl(): string {
  const base = import.meta.env.BASE_URL ?? "/";
  const normalised = base.endsWith("/") ? base : `${base}/`;
  return `${normalised}pdfjs-wasm/`;
}

/** Diagnostic-only: forces a full-file PDF.js load (no range/stream/prefetch). */
export function isPdfjsIsolationMode(): boolean {
  return envFlag("VITE_PDFJS_ISOLATION_MODE");
}

/**
 * Synthetic alignment overlay is a coordinate-test tool only.
 * Shown when DEV and `VITE_SHOW_ALIGNMENT_OVERLAY=true` (or Vitest/Playwright
 * explicitly opt in via the same env).
 */
export function isAlignmentOverlayAvailable(): boolean {
  return Boolean(import.meta.env.DEV) && envFlag("VITE_SHOW_ALIGNMENT_OVERLAY");
}

export function getPdfjsMaxDevicePixelRatio(): number {
  return envNumber("VITE_PDFJS_MAX_DPR") ?? Number.POSITIVE_INFINITY;
}

export function buildGetDocumentOptions(url: string): {
  url: string;
  wasmUrl: string;
  disableRange?: boolean;
  disableStream?: boolean;
  disableAutoFetch?: boolean;
} {
  const base = {
    url,
    wasmUrl: getPdfjsWasmUrl(),
  };
  if (isPdfjsIsolationMode()) {
    return {
      ...base,
      disableRange: true,
      disableStream: true,
      disableAutoFetch: true,
    };
  }
  return base;
}

export function resolveDevicePixelRatio(windowDpr: number): number {
  const capped = Math.min(windowDpr > 0 ? windowDpr : 1, getPdfjsMaxDevicePixelRatio());
  return Number.isFinite(capped) && capped > 0 ? capped : 1;
}

export function isRenderingCancelledError(cause: unknown): boolean {
  if (!cause || typeof cause !== "object") {
    return false;
  }
  const name = "name" in cause ? String((cause as { name?: unknown }).name) : "";
  const message = "message" in cause ? String((cause as { message?: unknown }).message) : "";
  return (
    name === "RenderingCancelledException" ||
    message.includes("Rendering cancelled") ||
    message.includes("RenderingCancelledException")
  );
}

/** Sample whether a canvas looks blank (all near-white / transparent). */
export function canvasLooksBlank(
  canvas: HTMLCanvasElement,
  options: { sampleStep?: number; whiteThreshold?: number } = {},
): boolean {
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context || canvas.width < 1 || canvas.height < 1) {
    return true;
  }
  const step = options.sampleStep ?? 8;
  const whiteThreshold = options.whiteThreshold ?? 245;
  const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
  let ink = 0;
  for (let y = 0; y < canvas.height; y += step) {
    for (let x = 0; x < canvas.width; x += step) {
      const index = (y * canvas.width + x) * 4;
      const r = data[index] ?? 0;
      const g = data[index + 1] ?? 0;
      const b = data[index + 2] ?? 0;
      const a = data[index + 3] ?? 0;
      if (a > 8 && (r < whiteThreshold || g < whiteThreshold || b < whiteThreshold)) {
        ink += 1;
      }
    }
  }
  return ink === 0;
}
