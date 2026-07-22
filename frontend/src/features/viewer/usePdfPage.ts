// Loads a single PDF.js page proxy from an already-loaded document.
//
// Like `usePdfDocument`, this is plain React state rather than TanStack
// Query: a `PDFPageProxy` is a live handle scoped to its parent document, not
// cacheable server data.

import { useEffect, useState } from "react";

import type { PDFDocumentProxy, PDFPageProxy } from "./pdfjs";

export interface UsePdfPageResult {
  readonly page: PDFPageProxy | undefined;
  readonly isLoading: boolean;
  readonly error: Error | null;
}

export function usePdfPage(
  pdfDocument: PDFDocumentProxy | undefined,
  pageNumber: number,
): UsePdfPageResult {
  const [page, setPage] = useState<PDFPageProxy | undefined>(undefined);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    if (!pdfDocument || !Number.isInteger(pageNumber) || pageNumber < 1) {
      setPage(undefined);
      setError(null);
      setIsLoading(false);
      return;
    }
    if (pageNumber > pdfDocument.numPages) {
      setPage(undefined);
      setError(new Error(`Page ${pageNumber} does not exist in this document.`));
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setError(null);
    setIsLoading(true);

    pdfDocument
      .getPage(pageNumber)
      .then((loadedPage) => {
        if (cancelled) {
          return;
        }
        setPage(loadedPage);
        setIsLoading(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) {
          return;
        }
        setError(cause instanceof Error ? cause : new Error("Failed to load the page."));
        setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [pdfDocument, pageNumber]);

  return { page, isLoading, error };
}
