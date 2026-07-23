// Renders a single canonical PDF page onto a high-DPI <canvas>.
//
// Render lifecycle (Phase 2 blank-page fix):
// - One active RenderTask per canvas; prior task is cancelled and awaited
//   before the canvas backing store is resized (resize clears pixels).
// - Monotonic render-generation tokens discard stale completions.
// - Cleanup cancels work but does not clear the canvas from a stale effect.
// - Failures surface an explicit error + retry instead of a silent white page.

import { Alert, Box, Button, Stack, Typography } from "@mui/material";
import { useCallback, useEffect, useRef, useState } from "react";

import type { CanonicalPageMetadata } from "./viewerApi";
import { computeEffectivePageDimensions, dimensionsExceedTolerance } from "./geometry";
import { DIMENSION_TOLERANCE_POINTS, type RotationDegrees } from "./constants";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask } from "./pdfjs";
import {
  canvasLooksBlank,
  isRenderingCancelledError,
  resolveDevicePixelRatio,
  type PdfRenderDiagnosticCode,
  type PdfRenderStatus,
} from "./pdfjsConfig";

function normalizeRotation(value: number): RotationDegrees {
  const wrapped = ((value % 360) + 360) % 360;
  return (
    wrapped === 0 || wrapped === 90 || wrapped === 180 || wrapped === 270 ? wrapped : 0
  ) as RotationDegrees;
}

async function cancelRenderTask(task: RenderTask | null): Promise<void> {
  if (!task) {
    return;
  }
  try {
    task.cancel();
  } catch {
    // cancel() is idempotent on settled tasks in practice.
  }
  try {
    await task.promise;
  } catch (cause: unknown) {
    if (!isRenderingCancelledError(cause)) {
      // Ignore non-cancel failures from a task we intentionally abandoned.
    }
  }
}

export interface PdfCanvasRenderedViewport {
  readonly widthPx: number;
  readonly heightPx: number;
  readonly totalRotation: RotationDegrees;
}

export interface PdfCanvasProps {
  readonly page: PDFPageProxy | undefined;
  readonly pdfDocument?: PDFDocumentProxy;
  readonly pageNumber: number;
  readonly pageCount: number;
  readonly scale: number;
  readonly rotation: RotationDegrees;
  readonly backendPage?: CanonicalPageMetadata;
  /** When true (default), a fully white canvas after render is treated as failure. */
  readonly expectVisibleContent?: boolean;
  readonly documentId?: string | null;
  readonly onViewportChange?: (viewport: PdfCanvasRenderedViewport) => void;
  readonly onDimensionMismatchChange?: (mismatch: boolean) => void;
  readonly onRenderStatusChange?: (status: PdfRenderStatus) => void;
}

export function PdfCanvas({
  page,
  pdfDocument,
  pageNumber,
  pageCount,
  scale,
  rotation,
  backendPage,
  expectVisibleContent = true,
  documentId = null,
  onViewportChange,
  onDimensionMismatchChange,
  onRenderStatusChange,
}: PdfCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const renderTaskRef = useRef<RenderTask | null>(null);
  const renderGenerationRef = useRef(0);
  const [renderStatus, setRenderStatus] = useState<PdfRenderStatus>("idle");
  const [diagnosticCode, setDiagnosticCode] = useState<PdfRenderDiagnosticCode>(null);
  const [retryToken, setRetryToken] = useState(0);

  const updateStatus = useCallback(
    (status: PdfRenderStatus) => {
      setRenderStatus(status);
      onRenderStatusChange?.(status);
    },
    [onRenderStatusChange],
  );

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
      updateStatus("idle");
      return;
    }

    const generation = ++renderGenerationRef.current;
    let effectActive = true;

    const run = async () => {
      updateStatus("rendering");
      setDiagnosticCode(null);

      await cancelRenderTask(renderTaskRef.current);
      renderTaskRef.current = null;

      if (!effectActive || renderGenerationRef.current !== generation) {
        return;
      }

      if (!Number.isFinite(scale) || scale <= 0) {
        // Fit modes may briefly report scale 0 until the container is measured.
        updateStatus("idle");
        return;
      }

      const totalRotation = normalizeRotation(page.rotate + rotation);
      const viewport = page.getViewport({ scale, rotation: totalRotation });
      const context = canvas.getContext("2d");
      if (!context) {
        setDiagnosticCode("PDFJS_NO_CONTEXT");
        updateStatus("error");
        return;
      }

      const dpr = resolveDevicePixelRatio(
        typeof window !== "undefined" ? window.devicePixelRatio || 1 : 1,
      );
      const cssWidth = viewport.width;
      const cssHeight = viewport.height;
      const backingWidth = Math.max(1, Math.floor(cssWidth * dpr));
      const backingHeight = Math.max(1, Math.floor(cssHeight * dpr));

      if (
        !Number.isFinite(cssWidth) ||
        !Number.isFinite(cssHeight) ||
        cssWidth <= 0 ||
        cssHeight <= 0 ||
        backingWidth < 1 ||
        backingHeight < 1
      ) {
        setDiagnosticCode("PDFJS_INVALID_VIEWPORT");
        updateStatus("error");
        return;
      }

      if (!effectActive || renderGenerationRef.current !== generation) {
        return;
      }

      // Resize only after the prior task has settled — this clears pixels.
      canvas.width = backingWidth;
      canvas.height = backingHeight;
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${cssHeight}px`;

      const transform = dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined;
      const intent = "display";
      const optionalContentConfigPromise = pdfDocument
        ? pdfDocument.getOptionalContentConfig({ intent })
        : undefined;

      // pdfjs-dist 6 recommends the `canvas` parameter (not canvasContext).
      const renderTask = page.render({
        canvas,
        viewport,
        transform,
        intent,
        background: "rgb(255,255,255)",
        ...(optionalContentConfigPromise ? { optionalContentConfigPromise } : {}),
      });
      renderTaskRef.current = renderTask;

      try {
        await renderTask.promise;
        if (!effectActive || renderGenerationRef.current !== generation) {
          return;
        }
        if (expectVisibleContent && canvasLooksBlank(canvas)) {
          const sampleStep = 8;
          const sampled =
            Math.ceil(canvas.width / sampleStep) * Math.ceil(canvas.height / sampleStep);
          if (import.meta.env.DEV) {
            console.info("[pdfjs] blank_render_detected", {
              document_id: documentId,
              canvas_width: canvas.width,
              canvas_height: canvas.height,
              sampled_pixel_count: sampled,
              non_white_pixel_ratio: 0,
              blank_render_detected: true,
            });
          }
          setDiagnosticCode("PDFJS_BLANK_PAGE");
          updateStatus("error");
          return;
        }
        if (import.meta.env.DEV) {
          console.info("[pdfjs] render_task_completed", {
            document_id: documentId,
            page_number: pageNumber,
          });
        }
        updateStatus("rendered");
        onViewportChange?.({
          widthPx: cssWidth,
          heightPx: cssHeight,
          totalRotation,
        });
      } catch (cause: unknown) {
        if (isRenderingCancelledError(cause)) {
          if (import.meta.env.DEV) {
            console.info("[pdfjs] render_task_cancelled", {
              document_id: documentId,
              page_number: pageNumber,
            });
          }
          return;
        }
        if (!effectActive || renderGenerationRef.current !== generation) {
          return;
        }
        if (import.meta.env.DEV) {
          const err = cause instanceof Error ? cause : null;
          console.info("[pdfjs] render_task_failed", {
            document_id: documentId,
            page_number: pageNumber,
            pdfjs_error_name: err?.name ?? "unknown",
            pdfjs_error_message_safe: (err?.message ?? "render failed").slice(0, 200),
          });
        }
        setDiagnosticCode("PDFJS_RENDER_FAILED");
        updateStatus("error");
      } finally {
        if (renderTaskRef.current === renderTask) {
          renderTaskRef.current = null;
        }
      }
    };

    void run();

    return () => {
      effectActive = false;
      // Abandon this generation so a late await cannot update UI/canvas sizing.
      if (renderGenerationRef.current === generation) {
        renderGenerationRef.current += 1;
      }
      const task = renderTaskRef.current;
      if (task) {
        try {
          task.cancel();
        } catch {
          // ignore
        }
      }
      // Intentionally do not clear canvas.width/height here.
    };
  }, [
    page,
    pdfDocument,
    scale,
    rotation,
    onViewportChange,
    updateStatus,
    retryToken,
    expectVisibleContent,
    documentId,
    pageNumber,
  ]);

  const handleRetry = () => {
    setRetryToken((token) => token + 1);
  };

  return (
    <Stack spacing={1} sx={{ alignItems: "center" }}>
      <Box sx={{ display: "inline-block", boxShadow: 1, bgcolor: "background.paper" }}>
        <canvas
          ref={canvasRef}
          role="img"
          aria-busy={renderStatus === "rendering"}
          aria-label={
            renderStatus === "rendered"
              ? `Page ${pageNumber} of ${pageCount} of the canonical document.`
              : renderStatus === "error"
                ? `Page ${pageNumber} of ${pageCount} failed to render.`
                : `Page ${pageNumber} of ${pageCount} is rendering.`
          }
          data-render-status={renderStatus}
        />
      </Box>
      {renderStatus === "error" ? (
        <Alert
          severity="error"
          action={
            <Button color="inherit" size="small" onClick={handleRetry}>
              Retry
            </Button>
          }
          sx={{ maxWidth: 480 }}
        >
          <Typography component="div" variant="body2">
            Canonical document could not be rendered.
          </Typography>
          {diagnosticCode ? (
            <Typography component="div" variant="caption" sx={{ display: "block", mt: 0.5 }}>
              Error code: {diagnosticCode} · stage: canvas render
            </Typography>
          ) : null}
        </Alert>
      ) : null}
    </Stack>
  );
}

/** Test helper: cancel + await a RenderTask without touching the canvas. */
export const __testables = {
  cancelRenderTask,
  normalizeRotation,
};
