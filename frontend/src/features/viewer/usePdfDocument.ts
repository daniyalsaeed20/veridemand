// Loads a PDF.js document proxy for a canonical PDF URL.
//
// This intentionally does *not* use TanStack Query: a `PDFDocumentProxy` is a
// live resource (backed by a worker + network transport) that must be
// explicitly destroyed, not cached JSON. Plain React state keeps that
// lifecycle explicit and easy to reason about.
//
// Monotonic load generations ensure Strict Mode remounts and rapid document
// switches cannot let a stale task clear a newer successful render.

import { useCallback, useEffect, useRef, useState } from "react";

import { getDocument, type PDFDocumentProxy } from "./pdfjs";
import { buildGetDocumentOptions, getPdfjsWasmUrl } from "./pdfjsConfig";

export interface UsePdfDocumentResult {
  readonly pdfDocument: PDFDocumentProxy | undefined;
  readonly isLoading: boolean;
  readonly error: Error | null;
  readonly loadGeneration: number;
  readonly retry: () => void;
}

function logPdfjsDev(event: string, fields: Record<string, unknown>): void {
  if (!import.meta.env.DEV) {
    return;
  }
  // Never log the PDF URL (may contain sensitive query data).
  console.info(`[pdfjs] ${event}`, fields);
}

function safeErrorMessage(cause: unknown): string {
  if (cause instanceof Error) {
    return cause.message.slice(0, 200);
  }
  return "Failed to load the canonical PDF.";
}

export function usePdfDocument(
  url: string | null,
  documentId: string | null = null,
): UsePdfDocumentResult {
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [loadGeneration, setLoadGeneration] = useState(0);
  const [retryToken, setRetryToken] = useState(0);
  const generationRef = useRef(0);

  const retry = useCallback(() => {
    setRetryToken((token) => token + 1);
  }, []);

  useEffect(() => {
    if (!url) {
      setPdfDocument(undefined);
      setError(null);
      setIsLoading(false);
      return;
    }

    const generation = ++generationRef.current;
    setLoadGeneration(generation);
    let activeDocument: PDFDocumentProxy | undefined;
    setPdfDocument(undefined);
    setError(null);
    setIsLoading(true);

    logPdfjsDev("loading_task_started", {
      document_id: documentId,
      load_generation: generation,
      canonical_url_created: true,
      worker_src_configured: true,
      wasm_url: getPdfjsWasmUrl(),
    });

    const loadingTask = getDocument(buildGetDocumentOptions(url));

    loadingTask.promise
      .then((doc) => {
        if (generationRef.current !== generation) {
          doc.cleanup();
          return;
        }
        activeDocument = doc;
        setPdfDocument(doc);
        setIsLoading(false);
        logPdfjsDev("loading_task_resolved", {
          document_id: documentId,
          load_generation: generation,
          page_count: doc.numPages,
        });
      })
      .catch((cause: unknown) => {
        if (generationRef.current !== generation) {
          return;
        }
        const err = cause instanceof Error ? cause : new Error("Failed to load the canonical PDF.");
        setError(err);
        setIsLoading(false);
        logPdfjsDev("loading_task_failed", {
          document_id: documentId,
          load_generation: generation,
          pdfjs_error_name: err.name,
          pdfjs_error_message_safe: safeErrorMessage(cause),
        });
      });

    return () => {
      // Do not bump generation here — Strict Mode replay must not invalidate
      // the replacement effect's generation. Only destroy the abandoned task.
      const superseded = generationRef.current !== generation;
      logPdfjsDev("loading_task_destroyed", {
        document_id: documentId,
        load_generation: generation,
        superseded,
      });
      void loadingTask.destroy().catch(() => undefined);
      if (activeDocument && superseded) {
        activeDocument.cleanup();
      }
    };
  }, [url, documentId, retryToken]);

  return { pdfDocument, isLoading, error, loadGeneration, retry };
}
