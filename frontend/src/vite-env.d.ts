/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  /** Diagnostic-only: disable PDF.js range/stream/auto-fetch. */
  readonly VITE_PDFJS_ISOLATION_MODE?: string;
  /** Cap devicePixelRatio during blank-page diagnosis (e.g. "1"). */
  readonly VITE_PDFJS_MAX_DPR?: string;
  /** Show the synthetic alignment overlay in DEV (coordinate test only). */
  readonly VITE_SHOW_ALIGNMENT_OVERLAY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
