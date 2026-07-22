// Loads a PDF.js document proxy for a canonical PDF URL.
//
// This intentionally does *not* use TanStack Query: a `PDFDocumentProxy` is a
// live resource (backed by a worker + network transport) that must be
// explicitly destroyed, not cached JSON. Plain React state keeps that
// lifecycle explicit and easy to reason about.

import { useEffect, useState } from "react";

import { getDocument, type PDFDocumentProxy } from "./pdfjs";

export interface UsePdfDocumentResult {
  readonly pdfDocument: PDFDocumentProxy | undefined;
  readonly isLoading: boolean;
  readonly error: Error | null;
}

export function usePdfDocument(url: string | null): UsePdfDocumentResult {
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!url) {
      setPdfDocument(undefined);
      setError(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setPdfDocument(undefined);
    setError(null);
    setIsLoading(true);

    const loadingTask = getDocument({ url });

    loadingTask.promise
      .then((doc) => {
        if (cancelled) {
          // `loadingTask.destroy()` below already tears down the transport;
          // nothing further to release on the document itself.
          return;
        }
        setPdfDocument(doc);
        setIsLoading(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) {
          return;
        }
        setError(cause instanceof Error ? cause : new Error("Failed to load the canonical PDF."));
        setIsLoading(false);
      });

    return () => {
      cancelled = true;
      // Aborts in-flight network requests and destroys the underlying
      // document/worker transport regardless of load state.
      void loadingTask.destroy().catch(() => undefined);
    };
  }, [url]);

  return { pdfDocument, isLoading, error };
}
