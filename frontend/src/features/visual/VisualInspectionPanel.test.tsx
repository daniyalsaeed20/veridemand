import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { VisualDocumentSummary, VisualPageResult } from "../../contracts";
import { VisualInspectionPanel } from "./VisualInspectionPanel";

const summary = {
  document_id: "doc_" + "a".repeat(32),
  visual_processing_status: "visual_processing_complete",
  page_count: 1,
  pages_selected: 1,
  pages_completed: 1,
  pages_no_text: 0,
  pages_failed: 0,
  pages_cancelled: 0,
  native_pages_retained: 0,
  native_pages_downgraded: 0,
  visual_result_available: true,
  handwriting_assessment_pending: true,
  final_result_available: false,
  document_source_policy: "visual_authority",
  progress: { percent: 65, pages_completed: 1, pages_total: 1 },
  page_summaries: [],
  warnings: [],
  created_at: new Date().toISOString(),
} as VisualDocumentSummary;

const page = {
  page_number: 1,
  status: "completed",
  source_mode: "visual_authority",
  line_count: 1,
  word_count: 2,
  visual_result_available: true,
  lines: [
    {
      id: "ocrline_p0001_000001",
      page_number: 1,
      normalised_text: "Hello OCR",
      detection_score: 0.9,
      recognition_score: 0.95,
      bbox: { x: 0.1, y: 0.1, width: 0.4, height: 0.05 },
      polygon: {
        points: [
          { x: 0.1, y: 0.1 },
          { x: 0.5, y: 0.1 },
          { x: 0.5, y: 0.15 },
          { x: 0.1, y: 0.15 },
        ],
      },
      pixel_bbox: { x: 10, y: 10, width: 40, height: 5 },
      pixel_polygon: {
        points: [
          { x: 10, y: 10 },
          { x: 50, y: 10 },
          { x: 50, y: 15 },
          { x: 10, y: 15 },
        ],
      },
      preprocessing_variant: "original_rgb",
    },
  ],
  words: [],
  warnings: [],
} as unknown as VisualPageResult;

describe("VisualInspectionPanel", () => {
  it("shows provisional notices and OCR text", () => {
    render(
      <VisualInspectionPanel
        summary={summary}
        page={page}
        ocrLineOverlayEnabled={false}
        ocrWordOverlayEnabled={false}
        onToggleOcrLineOverlay={vi.fn()}
        onToggleOcrWordOverlay={vi.fn()}
      />,
    );
    expect(screen.getByText(/Printed OCR result — provisional/i)).toBeInTheDocument();
    expect(screen.getByText(/Handwriting has not yet been assessed/i)).toBeInTheDocument();
    expect(screen.getByText("Hello OCR")).toBeInTheDocument();
    expect(screen.getByText(/Show OCR line boxes/i)).toBeInTheDocument();
  });
});
