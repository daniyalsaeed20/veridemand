import { useEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
import {
  canonicalViewUrl,
  listPages,
  listSpans,
  retryOcrPage,
  thumbnailUrl,
  type DocumentPage,
  type SourceSpan,
} from "../api/client";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

type Props = {
  sessionId: string;
  documentId: string;
  displayName: string;
  focusPage?: number | null;
  focusSpanIds?: string[] | null;
};

function polygonToScreen(
  polygon: number[][],
  width: number,
  height: number,
): { left: number; top: number; width: number; height: number } {
  const xs = polygon.map((p) => p[0] ?? 0);
  const ys = polygon.map((p) => p[1] ?? 0);
  const left = Math.min(...xs) * width;
  const top = Math.min(...ys) * height;
  const right = Math.max(...xs) * width;
  const bottom = Math.max(...ys) * height;
  return { left, top, width: right - left, height: bottom - top };
}

export default function DocumentViewer({
  sessionId,
  documentId,
  displayName,
  focusPage = null,
  focusSpanIds = null,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [pages, setPages] = useState<DocumentPage[]>([]);
  const [spans, setSpans] = useState<SourceSpan[]>([]);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1.25);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [highlightIds, setHighlightIds] = useState<string[]>([]);
  const [renderSize, setRenderSize] = useState({ width: 0, height: 0 });
  const [error, setError] = useState<string | null>(null);
  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);

  useEffect(() => {
    if (focusPage != null && focusPage >= 1) {
      setPageNumber(focusPage);
    }
    if (focusSpanIds && focusSpanIds.length > 0) {
      setHighlightIds(focusSpanIds);
      setSelectedSpanId(focusSpanIds[0] ?? null);
    }
  }, [focusPage, focusSpanIds]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setSelectedSpanId(null);
    setPageNumber(1);
    void (async () => {
      try {
        const pageList = await listPages(sessionId, documentId);
        if (cancelled) return;
        setPages(pageList);
        const url = canonicalViewUrl(sessionId, documentId);
        const loading = pdfjs.getDocument(url);
        const pdf = await loading.promise;
        if (cancelled) {
          await pdf.destroy();
          return;
        }
        setPdfDoc(pdf);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to open document viewer");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, documentId]);

  useEffect(() => {
    return () => {
      void pdfDoc?.destroy();
    };
  }, [pdfDoc]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const pageSpans = await listSpans(sessionId, documentId, pageNumber);
        if (!cancelled) setSpans(pageSpans);
      } catch {
        if (!cancelled) setSpans([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, documentId, pageNumber]);

  useEffect(() => {
    if (!pdfDoc || !canvasRef.current) return;
    let cancelled = false;
    void (async () => {
      try {
        const page = await pdfDoc.getPage(pageNumber);
        if (cancelled) return;
        const viewport = page.getViewport({ scale: zoom });
        const canvas = canvasRef.current;
        if (!canvas) return;
        const context = canvas.getContext("2d");
        if (!context) return;
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        setRenderSize({ width: viewport.width, height: viewport.height });
        await page.render({ canvasContext: context, viewport }).promise;
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to render page");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfDoc, pageNumber, zoom]);

  const currentPage = pages.find((p) => p.page_number === pageNumber) ?? null;
  const highlightSpans = spans.filter(
    (s) => highlightIds.includes(s.id) || s.id === selectedSpanId,
  );
  const pageCount = pages.length || pdfDoc?.numPages || 0;

  return (
    <div className="viewer">
      <div className="viewer-toolbar">
        <strong>{displayName}</strong>
        <div className="viewer-controls">
          <button
            type="button"
            className="btn btn-small"
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((n) => Math.max(1, n - 1))}
          >
            Prev
          </button>
          <span className="muted">
            Page {pageNumber} / {pageCount || "—"}
          </span>
          <button
            type="button"
            className="btn btn-small"
            disabled={pageNumber >= pageCount}
            onClick={() => setPageNumber((n) => Math.min(pageCount, n + 1))}
          >
            Next
          </button>
          <button
            type="button"
            className="btn btn-small"
            onClick={() => setZoom((z) => Math.max(0.5, z - 0.25))}
          >
            −
          </button>
          <span className="muted">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            className="btn btn-small"
            onClick={() => setZoom((z) => Math.min(3, z + 0.25))}
          >
            +
          </button>
        </div>
      </div>

      {currentPage ? (
        <p className="viewer-meta muted">
          Route: {currentPage.route}
          {currentPage.extraction_method
            ? ` · extraction: ${currentPage.extraction_method === "ocr" ? "OCR" : currentPage.extraction_method === "native" ? "Native" : currentPage.extraction_method}`
            : ""}
          {currentPage.ocr_status === "pending" ? " · OCR queued/processing" : ""}
          {currentPage.ocr_status === "done" ? " · OCR completed" : ""}
          {currentPage.ocr_status === "failed" ? " · OCR failed — page remains viewable" : ""}
          {currentPage.quality_flags.includes("low_confidence")
            ? " · recognition warning (not legal verification)"
            : ""}
          {currentPage.quality_flags.length > 0
            ? ` · flags: ${currentPage.quality_flags.join(", ")}`
            : ""}
        </p>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="viewer-body">
        <div className="thumb-rail" aria-label="Page thumbnails">
          {pages.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`thumb${p.page_number === pageNumber ? " thumb-active" : ""}`}
              onClick={() => setPageNumber(p.page_number)}
            >
              <img
                src={thumbnailUrl(sessionId, documentId, p.page_number)}
                alt={`Page ${p.page_number}`}
              />
              <span>
                {p.page_number}
                {p.ocr_status === "pending" ? "…" : ""}
                {p.quality_flags.includes("low_confidence") ? "!" : ""}
              </span>
            </button>
          ))}
        </div>

        <div className="page-stage">
          <div className="page-stack" style={{ width: renderSize.width || undefined }}>
            <canvas ref={canvasRef} className="pdf-canvas" />
            {highlightSpans.map((span) =>
              span.polygons.map((poly, i) => {
                const box = polygonToScreen(poly, renderSize.width, renderSize.height);
                return (
                  <div
                    key={`${span.id}-${i}`}
                    className="highlight"
                    style={{
                      left: box.left,
                      top: box.top,
                      width: box.width,
                      height: box.height,
                    }}
                  />
                );
              }),
            )}
          </div>
        </div>

        <div className="span-panel">
          <h3>Source spans</h3>
          {currentPage?.ocr_status === "pending" ? (
            <p className="muted">OCR in progress for this page…</p>
          ) : null}
          {currentPage?.ocr_status === "failed" ? (
            <p className="muted">
              OCR failed for this page
              {currentPage.quality_flags.includes("insufficient_coverage")
                ? " (insufficient coverage — review required)"
                : ""}
              . The page remains viewable for manual review. Recognition confidence is not factual
              verification.
            </p>
          ) : null}
          {currentPage?.quality_flags.includes("insufficient_coverage") &&
          currentPage.ocr_status !== "failed" ? (
            <p className="muted">
              OCR under-detection: coverage is incomplete for this page. Not treated as fully usable
              evidence.
            </p>
          ) : null}
          {currentPage?.route === "ocr" &&
          currentPage.ocr_status === "done" &&
          spans.length === 0 ? (
            <p className="muted">OCR completed with no published spans.</p>
          ) : null}
          {spans.length === 0 && currentPage?.ocr_status !== "pending" ? (
            <p className="muted">No source spans on this page.</p>
          ) : (
            <ul>
              {spans.map((span) => (
                <li key={span.id}>
                  <button
                    type="button"
                    className={`span-item${selectedSpanId === span.id ? " span-item-active" : ""}`}
                    onClick={() => setSelectedSpanId(span.id)}
                  >
                    <span className="muted">
                      [
                      {span.method === "ocr"
                        ? "OCR"
                        : span.method === "native"
                          ? "Native"
                          : span.method}
                      {span.confidence != null ? ` · conf ${span.confidence.toFixed(2)}` : ""}]
                    </span>{" "}
                    {span.text.slice(0, 120) || "(empty)"}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {currentPage?.ocr_status === "failed" ||
          currentPage?.quality_flags.includes("low_confidence") ||
          currentPage?.quality_flags.includes("insufficient_coverage") ? (
            <button
              type="button"
              className="btn btn-small"
              onClick={() => {
                void (async () => {
                  try {
                    await retryOcrPage(sessionId, documentId, pageNumber);
                    const pageList = await listPages(sessionId, documentId);
                    setPages(pageList);
                    const pageSpans = await listSpans(sessionId, documentId, pageNumber);
                    setSpans(pageSpans);
                  } catch (err) {
                    setError(err instanceof Error ? err.message : "OCR retry failed");
                  }
                })();
              }}
            >
              Retry OCR
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
