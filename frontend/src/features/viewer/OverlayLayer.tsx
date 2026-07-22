// Absolute-positioned SVG overlay for the Phase 2 synthetic alignment proof.
//
// - Always `pointer-events: none` so it never blocks interaction with the
//   canvas or toolbar underneath it.
// - Every item is explicitly labelled as synthetic — this is an alignment
//   proof, never real extraction output (doctrine: no unsupported facts).
// - Positioned in absolute pixels matching the last rendered canvas viewport
//   (`pixelWidth`/`pixelHeight`), with the same rotation already baked into
//   the geometry via `rotateNormalizedRect`.

import { Box, Typography } from "@mui/material";

import { rotateNormalizedRect, scaleRectToPixels } from "./geometry";
import type { RotationDegrees } from "./constants";
import type { OverlayProofItem } from "./viewerApi";
import type { NativeWord } from "../../contracts";

export interface OverlayLayerProps {
  readonly overlays: readonly OverlayProofItem[];
  readonly nativeWordOverlays?: readonly NativeWord[];
  readonly pageNumber: number;
  readonly pixelWidth: number;
  readonly pixelHeight: number;
  readonly rotation: RotationDegrees;
  readonly enabled: boolean;
}

export function OverlayLayer({
  overlays,
  nativeWordOverlays = [],
  pageNumber,
  pixelWidth,
  pixelHeight,
  rotation,
  enabled,
}: OverlayLayerProps) {
  if (!enabled || pixelWidth <= 0 || pixelHeight <= 0) {
    return null;
  }

  const pageOverlays = overlays.filter((overlay) => overlay.page_number === pageNumber);
  const nativeWords = nativeWordOverlays.filter((word) => word.page_number === pageNumber);
  if (pageOverlays.length === 0 && nativeWords.length === 0) {
    return null;
  }

  return (
    <Box
      data-testid="overlay-layer"
      aria-hidden="true"
      sx={{
        position: "absolute",
        inset: 0,
        width: pixelWidth,
        height: pixelHeight,
        pointerEvents: "none",
      }}
    >
      <svg
        width={pixelWidth}
        height={pixelHeight}
        viewBox={`0 0 ${pixelWidth} ${pixelHeight}`}
        style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
      >
        {pageOverlays.map((overlay) => {
          const rotatedBbox = rotateNormalizedRect(overlay.geometry.bbox, rotation);
          const rect = scaleRectToPixels(rotatedBbox, pixelWidth, pixelHeight);
          return (
            <g key={overlay.id}>
              <title>{`${overlay.label} (coordinate test — synthetic alignment, not extracted data)`}</title>
              <rect
                x={rect.left}
                y={rect.top}
                width={rect.width}
                height={rect.height}
                fill="rgba(31, 78, 121, 0.12)"
                stroke="#1f4e79"
                strokeWidth={2}
                strokeDasharray="6 4"
              />
              <text
                x={rect.left + 4}
                y={Math.max(12, rect.top - 6)}
                fill="#1f4e79"
                fontSize={12}
                fontWeight={600}
              >
                {overlay.label} (coordinate test)
              </text>
            </g>
          );
        })}
        {nativeWords.map((word) => {
          const rotatedBbox = rotateNormalizedRect(word.geometry.bbox, rotation);
          const rect = scaleRectToPixels(rotatedBbox, pixelWidth, pixelHeight);
          return (
            <g key={word.id}>
              <title>{`${word.text} (native_pdf_word — Native PDF boxes)`}</title>
              <rect
                x={rect.left}
                y={rect.top}
                width={rect.width}
                height={rect.height}
                fill="rgba(46, 125, 50, 0.10)"
                stroke="#2e7d32"
                strokeWidth={1}
              />
              <text
                x={rect.left + 2}
                y={Math.max(10, rect.top - 3)}
                fill="#2e7d32"
                fontSize={10}
                fontWeight={600}
              >
                Native PDF boxes
              </text>
            </g>
          );
        })}
      </svg>
      <Typography
        component="span"
        sx={{ position: "absolute", width: 1, height: 1, overflow: "hidden" }}
      >
        {`${pageOverlays.length} coordinate-test alignment overlay(s) and ${nativeWords.length} Native PDF boxes shown for page ${pageNumber}.`}
      </Typography>
    </Box>
  );
}
