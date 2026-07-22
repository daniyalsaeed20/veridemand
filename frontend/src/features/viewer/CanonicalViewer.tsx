// Two-column viewer body (Phase 2): orchestrates canonical metadata, the
// PDF.js document/page, the synthetic overlay proof and the ephemeral viewer
// UI state into one panel. Rendered by `SessionWorkspace` alongside the queue.

import { Card, CardContent, Divider, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { clampScale, computeFitPageScale, computeFitWidthScale } from "./geometry";
import { OverlayLayer } from "./OverlayLayer";
import { PageNavigation } from "./PageNavigation";
import { PdfCanvas, type PdfCanvasRenderedViewport } from "./PdfCanvas";
import { isAlignmentOverlayAvailable } from "./pdfjsConfig";
import { useCanonicalDocument, viewerKeys } from "./useCanonicalDocument";
import { usePdfDocument } from "./usePdfDocument";
import { usePdfPage } from "./usePdfPage";
import { ViewerEmptyState } from "./ViewerEmptyState";
import { ViewerToolbar } from "./ViewerToolbar";
import { canonicalPdfUrl, getOverlayProof, type DocumentSummary } from "./viewerApi";
import { getNativePage, getNativeSummary } from "./nativeApi";
import { NativeInspectionPanel } from "./NativeInspectionPanel";
import { useViewerStore } from "./viewerState";

export interface CanonicalViewerProps {
  readonly sessionId: string;
  readonly documents: readonly DocumentSummary[];
}

export function CanonicalViewer({ sessionId, documents }: CanonicalViewerProps) {
  const selectedDocumentId = useViewerStore((state) => state.selectedDocumentId);
  const pageNumber = useViewerStore((state) => state.pageNumber);
  const zoomMode = useViewerStore((state) => state.zoomMode);
  const manualScale = useViewerStore((state) => state.manualScale);
  const userRotation = useViewerStore((state) => state.userRotation);
  const overlayEnabled = useViewerStore((state) => state.overlayEnabled);
  const nativeOverlayEnabled = useViewerStore((state) => state.nativeOverlayEnabled);
  const setPageNumber = useViewerStore((state) => state.setPageNumber);
  const setZoomMode = useViewerStore((state) => state.setZoomMode);
  const zoomIn = useViewerStore((state) => state.zoomIn);
  const zoomOut = useViewerStore((state) => state.zoomOut);
  const rotateClockwise = useViewerStore((state) => state.rotateClockwise);
  const rotateCounterClockwise = useViewerStore((state) => state.rotateCounterClockwise);
  const toggleOverlay = useViewerStore((state) => state.toggleOverlay);
  const toggleNativeOverlay = useViewerStore((state) => state.toggleNativeOverlay);
  const selectDocument = useViewerStore((state) => state.selectDocument);

  const alignmentOverlayAvailable = isAlignmentOverlayAvailable();
  const overlayActive = alignmentOverlayAvailable && overlayEnabled;

  const selectedDocument = useMemo(
    () => documents.find((document) => document.document_id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId],
  );

  // If the selected document disappears from the queue (removed/session
  // reset), fall back to the empty state instead of pointing at nothing.
  useEffect(() => {
    if (selectedDocumentId && !selectedDocument) {
      selectDocument(null);
    }
  }, [selectedDocumentId, selectedDocument, selectDocument]);

  // Fit-width/fit-page measure the *viewer container*, never window width.
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      const { width, height } = entry.contentRect;
      setContainerSize({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const canonicalReady = Boolean(selectedDocument?.canonical_view_available);

  const metadataQuery = useCanonicalDocument(sessionId, selectedDocumentId, {
    enabled: canonicalReady,
  });

  const pdfUrl =
    canonicalReady && selectedDocumentId ? canonicalPdfUrl(sessionId, selectedDocumentId) : null;
  const { pdfDocument, error: pdfError } = usePdfDocument(pdfUrl);

  const pageCount = metadataQuery.data?.page_count ?? 1;
  const clampedPageNumber = Math.min(Math.max(1, pageNumber), pageCount);

  const { page } = usePdfPage(pdfDocument, clampedPageNumber);
  const nativeTrustComplete = selectedDocument?.status === "native_trust_complete";
  const nativeSummaryQuery = useQuery({
    queryKey:
      sessionId && selectedDocumentId
        ? ["viewer", "native-summary", sessionId, selectedDocumentId]
        : ["viewer", "native-summary", "disabled"],
    queryFn: ({ signal }) => getNativeSummary(sessionId, selectedDocumentId as string, signal),
    enabled: nativeTrustComplete && Boolean(selectedDocumentId),
    staleTime: Infinity,
    retry: false,
  });
  const nativePageQuery = useQuery({
    queryKey:
      sessionId && selectedDocumentId
        ? ["viewer", "native-page", sessionId, selectedDocumentId, clampedPageNumber]
        : ["viewer", "native-page", "disabled"],
    queryFn: ({ signal }) =>
      getNativePage(sessionId, selectedDocumentId as string, clampedPageNumber, signal),
    enabled: nativeTrustComplete && Boolean(selectedDocumentId) && nativeSummaryQuery.isSuccess,
    staleTime: Infinity,
    retry: false,
  });

  const overlayQuery = useQuery({
    queryKey:
      sessionId && selectedDocumentId
        ? viewerKeys.overlayProof(sessionId, selectedDocumentId)
        : ["viewer", "overlay-proof", "disabled"],
    queryFn: ({ signal }) => getOverlayProof(sessionId, selectedDocumentId as string, signal),
    enabled: canonicalReady && Boolean(selectedDocumentId) && overlayActive,
    staleTime: Infinity,
    retry: false,
  });

  const backendPage = metadataQuery.data?.pages.find(
    (candidate) => candidate.page_number === clampedPageNumber,
  );

  const [dimensionMismatch, setDimensionMismatch] = useState(false);
  const [renderedViewport, setRenderedViewport] = useState<PdfCanvasRenderedViewport | null>(null);

  useEffect(() => {
    // A new page is loading; discard the last rendered pixel size so the
    // overlay never briefly shows at the previous page's dimensions.
    setRenderedViewport(null);
  }, [page]);

  const handleViewportChange = useCallback((viewport: PdfCanvasRenderedViewport) => {
    setRenderedViewport(viewport);
  }, []);
  const handleDimensionMismatchChange = useCallback((mismatch: boolean) => {
    setDimensionMismatch(mismatch);
  }, []);

  const effectiveScale = useMemo(() => {
    if (!backendPage) {
      return clampScale(manualScale);
    }
    if (
      (zoomMode === "fit_width" || zoomMode === "fit_page") &&
      (containerSize.width < 1 || (zoomMode === "fit_page" && containerSize.height < 1))
    ) {
      // Wait for ResizeObserver before painting fit modes — avoids a min-scale
      // render that is immediately cancelled when the container measures.
      return 0;
    }
    switch (zoomMode) {
      case "manual":
        return clampScale(manualScale);
      case "fit_width":
        return computeFitWidthScale(
          containerSize.width,
          backendPage.width_points,
          backendPage.height_points,
          userRotation,
        );
      case "fit_page":
        return computeFitPageScale(
          containerSize.width,
          containerSize.height,
          backendPage.width_points,
          backendPage.height_points,
          userRotation,
        );
      default:
        return clampScale(manualScale);
    }
  }, [backendPage, zoomMode, manualScale, userRotation, containerSize]);

  const overlayDisabledReason = dimensionMismatch
    ? "Alignment overlay disabled: this page's rendered size does not match the canonical metadata within tolerance."
    : null;
  const nativeOverlayActive =
    nativeOverlayEnabled && nativePageQuery.data?.decision === "accepted" && !dimensionMismatch;

  let body: ReactNode;
  if (!selectedDocument) {
    body = <ViewerEmptyState variant="no_selection" />;
  } else if (!canonicalReady) {
    body = (
      <ViewerEmptyState
        variant={selectedDocument.canonical_status === "failed" ? "failed" : "not_ready"}
        title={
          selectedDocument.canonical_status === "failed" ? undefined : "Extraction has not started"
        }
      />
    );
  } else if (pdfError || metadataQuery.isError) {
    body = <ViewerEmptyState variant="load_error" />;
  } else if (!page || !backendPage) {
    body = (
      <ViewerEmptyState
        variant="not_ready"
        title="Loading canonical document..."
        description="Fetching page geometry and preparing the PDF renderer."
      />
    );
  } else {
    body = (
      <Stack spacing={2}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
        >
          <ViewerToolbar
            zoomMode={zoomMode}
            effectiveScale={effectiveScale}
            overlayEnabled={overlayActive}
            showOverlayControls={alignmentOverlayAvailable}
            overlayDisabledReason={overlayDisabledReason}
            onZoomModeChange={setZoomMode}
            onZoomIn={() => zoomIn(effectiveScale)}
            onZoomOut={() => zoomOut(effectiveScale)}
            onRotateClockwise={rotateClockwise}
            onRotateCounterClockwise={rotateCounterClockwise}
            onToggleOverlay={toggleOverlay}
          />
          <PageNavigation
            pageNumber={clampedPageNumber}
            pageCount={pageCount}
            onPageNumberChange={setPageNumber}
          />
        </Stack>

        <Divider />
        {nativeSummaryQuery.data ? (
          <NativeInspectionPanel
            summary={nativeSummaryQuery.data}
            page={nativePageQuery.data}
            nativeOverlayEnabled={nativeOverlayEnabled}
            onToggleNativeOverlay={toggleNativeOverlay}
            overlaysDisabled={dimensionMismatch}
          />
        ) : null}

        <Stack
          sx={{
            position: "relative",
            alignItems: "center",
            overflow: "auto",
            maxHeight: 720,
            py: 2,
          }}
        >
          <div style={{ position: "relative" }}>
            <PdfCanvas
              page={page}
              pdfDocument={pdfDocument}
              pageNumber={clampedPageNumber}
              pageCount={pageCount}
              scale={effectiveScale}
              rotation={userRotation}
              backendPage={backendPage}
              onViewportChange={handleViewportChange}
              onDimensionMismatchChange={handleDimensionMismatchChange}
            />
            <OverlayLayer
              overlays={overlayQuery.data?.overlays ?? []}
              nativeWordOverlays={nativeOverlayActive ? (nativePageQuery.data?.words ?? []) : []}
              pageNumber={clampedPageNumber}
              pixelWidth={renderedViewport?.widthPx ?? 0}
              pixelHeight={renderedViewport?.heightPx ?? 0}
              rotation={userRotation}
              enabled={(overlayActive || nativeOverlayActive) && !dimensionMismatch}
            />
          </div>
        </Stack>
      </Stack>
    );
  }

  return (
    <Card variant="outlined" sx={{ height: "100%" }}>
      <CardContent
        ref={containerRef}
        sx={{ display: "flex", flexDirection: "column", gap: 2, minHeight: 480 }}
      >
        <Typography variant="h2" component="h2">
          Canonical document
        </Typography>
        {body}
      </CardContent>
    </Card>
  );
}
