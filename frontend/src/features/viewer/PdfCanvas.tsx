// Renders a single canonical PDF page onto a high-DPI <canvas>.
//
// - `canvas.width`/`canvas.height` are set to the CSS viewport size multiplied
//   by `devicePixelRatio` so the page stays sharp on high-DPI displays; the
//   CSS box size is set separately to the un-scaled viewport dimensions.
// - Any in-flight `RenderTask` is cancelled before starting a new one or on
//   unmount, so rapid page/scale/rotation changes never race.
// - No `react-pdf`, no iframe: this talks to `pdfjs-dist` directly.

import { Box } from "@mui/material";
import { useEffect, useRef } from "react";

import type { CanonicalPageMetadata } from "./viewerApi";
import { computeEffectivePageDimensions, dimensionsExceedTolerance } from "./geometry";
import { DIMENSION_TOLERANCE_POINTS, type RotationDegrees } from "./constants";
import type { PDFPageProxy, RenderTask } from "./pdfjs";

// Normalises an arbitrary rotation sum (e.g. page.rotate + userRotation) back
// into the 0/90/180/270 range PDF.js and this feature always use.
function normalizeRotation(value: number): RotationDegrees {
  const wrapped = ((value % 360) + 360) % 360;
  return (
    wrapped === 0 || wrapped === 90 || wrapped === 180 || wrapped === 270 ? wrapped : 0
  ) as RotationDegrees;
}

export interface PdfCanvasRenderedViewport {
  readonly widthPx: number;
  readonly heightPx: number;
  readonly totalRotation: RotationDegrees;
}

export interface PdfCanvasProps {
  readonly page: PDFPageProxy | undefined;
  readonly pageNumber: number;
  readonly pageCount: number;
  readonly scale: number;
  readonly rotation: RotationDegrees;
  readonly backendPage?: CanonicalPageMetadata;
  readonly onViewportChange?: (viewport: PdfCanvasRenderedViewport) => void;
  readonly onDimensionMismatchChange?: (mismatch: boolean) => void;
}

export function PdfCanvas({
  page,
  pageNumber,
  pageCount,
  scale,
  rotation,
  backendPage,
  onViewportChange,
  onDimensionMismatchChange,
}: PdfCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const renderTaskRef = useRef<RenderTask | null>(null);

  // Dimension-tolerance check: compares PDF.js's own page geometry (accounting
  // for intrinsic rotation) against the backend canonical metadata for this
  // page. Runs independently of scale/rotation, which never affect the
  // page's intrinsic size.
  useEffect(() => {
    if (!page || !backendPage) {
      onDimensionMismatchChange?.(false);
      return;
    }
    const [x0, y0, x1, y1] = page.view;
    const rawWidth = Math.abs(x1 - x0);
    const rawHeight = Math.abs(y1 - y0);
    const intrinsicRotation = normalizeRotation(page.rotate);
    const effective = computeEffectivePageDimensions(rawWidth, rawHeight, intrinsicRotation);
    const mismatch = dimensionsExceedTolerance(
      effective.width,
      effective.height,
      backendPage.width_points,
      backendPage.height_points,
      DIMENSION_TOLERANCE_POINTS,
    );
    onDimensionMismatchChange?.(mismatch);
  }, [page, backendPage, onDimensionMismatchChange]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!page || !canvas) {
      return;
    }

    // Cancel any render still in flight before starting a new one.
    renderTaskRef.current?.cancel();
    renderTaskRef.current = null;

    const totalRotation = normalizeRotation(page.rotate + rotation);
    const viewport = page.getViewport({ scale, rotation: totalRotation });
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    const dpr = typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1;
    canvas.width = Math.max(1, Math.floor(viewport.width * dpr));
    canvas.height = Math.max(1, Math.floor(viewport.height * dpr));
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;

    const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined;
    const renderTask = page.render({ canvas, canvasContext: context, viewport, transform });
    renderTaskRef.current = renderTask;

    let cancelled = false;
    renderTask.promise
      .then(() => {
        if (!cancelled) {
          onViewportChange?.({ widthPx: viewport.width, heightPx: viewport.height, totalRotation });
        }
      })
      .catch(() => {
        // Expected when the render is cancelled below (RenderingCancelledException).
      });

    return () => {
      cancelled = true;
      renderTask.cancel();
      renderTaskRef.current = null;
    };
  }, [page, scale, rotation, onViewportChange]);

  return (
    <Box sx={{ display: "inline-block", boxShadow: 1, bgcolor: "background.paper" }}>
      <canvas
        ref={canvasRef}
        role="img"
        aria-label={`Page ${pageNumber} of ${pageCount} of the canonical document.`}
      />
    </Box>
  );
}
