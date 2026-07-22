import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PrintedOcrLine } from "../../contracts";
import { OcrOverlayLayer } from "./OcrOverlayLayer";

const line = {
  id: "ocrline_p0001_000001",
  page_number: 1,
  normalised_text: "Box",
  detection_score: 0.9,
  recognition_score: 0.9,
  bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.05 },
  polygon: {
    points: [
      { x: 0.1, y: 0.2 },
      { x: 0.4, y: 0.2 },
      { x: 0.4, y: 0.25 },
      { x: 0.1, y: 0.25 },
    ],
  },
  pixel_bbox: { x: 10, y: 20, width: 30, height: 5 },
  pixel_polygon: {
    points: [
      { x: 10, y: 20 },
      { x: 40, y: 20 },
      { x: 40, y: 25 },
      { x: 10, y: 25 },
    ],
  },
  preprocessing_variant: "original_rgb",
} as unknown as PrintedOcrLine;

describe("OcrOverlayLayer", () => {
  it("renders line boxes when enabled", () => {
    const { getByTestId } = render(
      <OcrOverlayLayer
        lines={[line]}
        words={[]}
        showLines
        showWords={false}
        pageNumber={1}
        pixelWidth={100}
        pixelHeight={100}
        rotation={0}
        enabled
      />,
    );
    expect(getByTestId("ocr-overlay-layer")).toBeInTheDocument();
  });

  it("renders nothing when disabled", () => {
    const { queryByTestId } = render(
      <OcrOverlayLayer
        lines={[line]}
        words={[]}
        showLines
        showWords={false}
        pageNumber={1}
        pixelWidth={100}
        pixelHeight={100}
        rotation={0}
        enabled={false}
      />,
    );
    expect(queryByTestId("ocr-overlay-layer")).toBeNull();
  });
});
