// Loads a PDF.js document proxy for a canonical PDF URL.
//
// This intentionally does *not* use TanStack Query: a `PDFDocumentProxy` is a
// live resource (backed by a worker + network transport) that must be
// explicitly destroyed, not cached JSON. Plain React state keeps that
// lifecycle explicit and easy to reason about.

import { useEffect, useState } from "react";

import { getDocument, type PDFDocumentProxy } from "./pdfjs";
import { buildGetDocumentOptions } from "./pdfjsConfig";

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
    let activeDocument: PDFDocumentProxy | undefined;
    setPdfDocument(undefined);
    setError(null);
    setIsLoading(true);

    const loadingTask = getDocument(buildGetDocumentOptions(url));

    loadingTask.promise
      .then((doc) => {
        if (cancelled) {
          doc.cleanup();
          return;
        }
        activeDocument = doc;
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
      if (activeDocument) {
        activeDocument.cleanup();
      }
    };
  }, [url]);

  return { pdfDocument, isLoading, error };
}
