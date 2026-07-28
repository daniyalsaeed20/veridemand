import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { VisualDocumentSummary, VisualPageResult } from "../../contracts";
import { VisualInspectionPanel } from "./VisualInspectionPanel";

const summary = {
  document_id: "doc_" + "a".repeat(32),
  visual_processing_status: "visual_processing_complete",
  page_count: 1,
  document_pages_total: 1,
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
  phase3_provisional_document_policy: "visual_authority",
  progress: { percent: 65, pages_completed: 1, pages_total: 1 },
  page_summaries: [],
  warnings: [],
  created_at: new Date().toISOString(),
} as VisualDocumentSummary;

const page = {
  page_number: 1,
  status: "completed",
  source_mode: "visual_authority",
  page_result_state: "full_visual_ocr",
  source_label: "Printed visual OCR",
  line_count: 1,
  word_count: 2,
  visual_result_available: true,
  visual_agreement_status: "not_required",
  recognition_agreement_status: "not_required",
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
    expect(screen.getByTestId("phase4-reconciled-policy")).toBeInTheDocument();
    expect(screen.getByText(/Handwriting has not yet been assessed/i)).toBeInTheDocument();
    expect(screen.getByTestId("visual-source-label")).toHaveTextContent("Printed visual OCR");
    expect(screen.getByRole("switch", { name: "Show line boxes" })).toBeInTheDocument();
  });

  it("labels verified embedded OCR and shows agreement status", () => {
    const embeddedPage = {
      ...page,
      source_mode: "embedded_ocr_authority",
      page_result_state: "embedded_ocr_verified",
      source_label: "Verified embedded OCR",
      visual_agreement_status: "passed",
      visual_agreement_score: 0.91,
      word_count: 3,
      line_count: 1,
    } as unknown as VisualPageResult;
    const embeddedSummary = {
      ...summary,
      document_source_policy: "embedded_ocr_authority",
      phase3_provisional_document_policy: "visual_authority",
      embedded_pages_verified: 1,
      pages_completed: 1,
    } as VisualDocumentSummary;
    render(
      <VisualInspectionPanel
        summary={embeddedSummary}
        page={embeddedPage}
        ocrLineOverlayEnabled={false}
        ocrWordOverlayEnabled={false}
        onToggleOcrLineOverlay={vi.fn()}
        onToggleOcrWordOverlay={vi.fn()}
      />,
    );
    expect(screen.getByTestId("visual-source-label")).toHaveTextContent("Verified embedded OCR");
    expect(screen.getByText(/Phase 4 embedded-text verification: passed/i)).toBeInTheDocument();
    expect(screen.getByTestId("phase3-provisional-policy")).toHaveTextContent("visual_authority");
  });

  it("shows an error for empty embedded authority instead of claiming success", () => {
    const emptyEmbedded = {
      ...page,
      source_mode: "embedded_ocr_authority",
      page_result_state: "embedded_ocr_verified",
      source_label: "Verified embedded OCR",
      visual_result_available: false,
      word_count: 0,
      line_count: 0,
      lines: [],
      words: [],
    } as unknown as VisualPageResult;
    render(
      <VisualInspectionPanel
        summary={summary}
        page={emptyEmbedded}
        ocrLineOverlayEnabled={false}
        ocrWordOverlayEnabled={false}
        onToggleOcrLineOverlay={vi.fn()}
        onToggleOcrWordOverlay={vi.fn()}
      />,
    );
    expect(screen.getByTestId("embedded-result-invalid")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Show word boxes" })).toBeDisabled();
  });

  it("shows concise isolated-glyph warning without quarantined strings", () => {
    const glyphPage = {
      ...page,
      source_mode: "native_authority",
      page_result_state: "digital_native",
      source_label: "Trusted digital text",
      page_route: "digital_native",
      route_reason_codes: ["trusted_digital_native_text", "isolated_glyphs_quarantined"],
      quarantined_glyph_count: 3,
      quarantined_region_count: 3,
      glyph_materiality: "non_material",
      phase3_page_decision: "accepted",
      visual_result_available: false,
      word_count: 0,
      line_count: 0,
      lines: [],
      words: [],
      warnings: [
        {
          code: "isolated_glyphs_quarantined",
          message: "Some unsupported symbols were excluded pending visual verification.",
        },
      ],
    } as unknown as VisualPageResult;
    render(
      <VisualInspectionPanel
        summary={{
          ...summary,
          document_source_policy: "native_authority",
          native_pages_retained: 1,
        }}
        page={glyphPage}
        ocrLineOverlayEnabled={false}
        ocrWordOverlayEnabled={false}
        onToggleOcrLineOverlay={vi.fn()}
        onToggleOcrWordOverlay={vi.fn()}
      />,
    );
    expect(screen.getByTestId("final-page-route")).toHaveTextContent("digital_native");
    expect(screen.getByTestId("visual-warnings")).toHaveTextContent(
      /unsupported symbols were excluded/i,
    );
    expect(screen.queryByText(/\ue001/)).not.toBeInTheDocument();
    expect(screen.queryByText(/private-use/i)).not.toBeInTheDocument();
  });
});
