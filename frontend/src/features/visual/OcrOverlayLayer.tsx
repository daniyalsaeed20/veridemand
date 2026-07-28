import { Box } from "@mui/material";

import type { PrintedOcrLine, PrintedOcrWord } from "../../contracts";
import type { RotationDegrees } from "../viewer/constants";
import { rotateNormalizedRect, scaleRectToPixels } from "../viewer/geometry";

export type OcrOverlayKind =
  "verified_embedded_ocr_word" | "printed_visual_ocr_word" | "targeted_repair_word";

export interface OcrOverlayLayerProps {
  readonly lines: readonly PrintedOcrLine[];
  readonly words: readonly PrintedOcrWord[];
  readonly showLines: boolean;
  readonly showWords: boolean;
  readonly pageNumber: number;
  readonly pixelWidth: number;
  readonly pixelHeight: number;
  readonly rotation: RotationDegrees;
  readonly enabled: boolean;
  readonly overlayKind?: OcrOverlayKind;
}

function lineTitle(kind: OcrOverlayKind, text: string): string {
  if (kind === "verified_embedded_ocr_word") {
    return `${text} (verified_embedded_ocr_line)`;
  }
  if (kind === "targeted_repair_word") {
    return `${text} (targeted_repair_line)`;
  }
  return `${text} (printed_visual_ocr_line)`;
}

function wordTitle(kind: OcrOverlayKind, text: string): string {
  if (kind === "verified_embedded_ocr_word") {
    return `${text} (verified_embedded_ocr_word)`;
  }
  if (kind === "targeted_repair_word") {
    return `${text} (targeted_repair_word)`;
  }
  return `${text} (printed_visual_ocr_word)`;
}

export function OcrOverlayLayer({
  lines,
  words,
  showLines,
  showWords,
  pageNumber,
  pixelWidth,
  pixelHeight,
  rotation,
  enabled,
  overlayKind = "printed_visual_ocr_word",
}: OcrOverlayLayerProps) {
  if (!enabled || pixelWidth <= 0 || pixelHeight <= 0) {
    return null;
  }

  const pageLines = showLines ? lines.filter((line) => line.page_number === pageNumber) : [];
  const pageWords = showWords ? words.filter((word) => word.page_number === pageNumber) : [];
  if (pageLines.length === 0 && pageWords.length === 0) {
    return null;
  }

  return (
    <Box
      data-testid="ocr-overlay-layer"
      data-overlay-source={overlayKind}
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
        {pageLines.map((line) => {
          const rotatedBbox = rotateNormalizedRect(line.bbox, rotation);
          const rect = scaleRectToPixels(rotatedBbox, pixelWidth, pixelHeight);
          return (
            <g key={line.id} data-overlay-kind="line" data-overlay-source={overlayKind}>
              <title>{lineTitle(overlayKind, line.normalised_text)}</title>
              <rect
                x={rect.left}
                y={rect.top}
                width={rect.width}
                height={rect.height}
                fill="rgba(2, 119, 189, 0.08)"
                stroke="#0277bd"
                strokeWidth={1.5}
              />
            </g>
          );
        })}
        {pageWords.map((word) => {
          const rotatedBbox = rotateNormalizedRect(word.bbox, rotation);
          const rect = scaleRectToPixels(rotatedBbox, pixelWidth, pixelHeight);
          return (
            <g key={word.id} data-overlay-kind="word" data-overlay-source={overlayKind}>
              <title>{wordTitle(overlayKind, word.normalised_text)}</title>
              <rect
                x={rect.left}
                y={rect.top}
                width={rect.width}
                height={rect.height}
                fill="rgba(0, 151, 167, 0.06)"
                stroke="#0097a7"
                strokeWidth={1}
                strokeDasharray="3 2"
              />
            </g>
          );
        })}
      </svg>
    </Box>
  );
}
