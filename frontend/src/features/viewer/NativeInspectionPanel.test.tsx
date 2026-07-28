import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { NativeDocumentSummary, NativePageResult } from "../../contracts";
import { NativeInspectionPanel } from "./NativeInspectionPanel";

const summary = {
  document_source_policy: "mixed_authority",
} as NativeDocumentSummary;

const metrics = {
  word_count: 2,
  character_count: 10,
} as NativePageResult["trust"]["metrics"];

const acceptedPage = {
  page_number: 1,
  decision: "accepted",
  source_mode: "native_authority",
  provisional_native_text: "Accepted native text",
  trust: {
    native_trust_score: 0.91,
    reason_codes: ["trust_passed"],
    metrics,
    native_result_available: true,
    visual_processing_required: false,
  },
} as NativePageResult;

describe("NativeInspectionPanel", () => {
  it("shows the Phase 3 labels and native box toggle for accepted pages", () => {
    const onToggleNativeOverlay = vi.fn();
    render(
      <NativeInspectionPanel
        summary={summary}
        page={acceptedPage}
        nativeOverlayEnabled={false}
        onToggleNativeOverlay={onToggleNativeOverlay}
      />,
    );

    expect(
      screen.getByText(/Phase 3 provisional document source policy: mixed_authority/),
    ).toBeInTheDocument();
    expect(screen.getByText("Phase 3 visual agreement: not evaluated")).toBeInTheDocument();
    expect(screen.getByText("Extraction order is provisional.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch", { name: "Show native word boxes" }));
    expect(onToggleNativeOverlay).toHaveBeenCalledOnce();
  });

  it("does not display rejected candidate text", () => {
    const rejectedPage = {
      ...acceptedPage,
      decision: "rejected",
      provisional_native_text: null,
      words: [],
    } as NativePageResult;
    render(
      <NativeInspectionPanel
        summary={summary}
        page={rejectedPage}
        nativeOverlayEnabled={false}
        onToggleNativeOverlay={vi.fn()}
      />,
    );

    expect(screen.getByText(/native text layer was rejected/i)).toBeInTheDocument();
    expect(screen.queryByText("Accepted native text")).toBeNull();
    expect(screen.queryByRole("switch", { name: "Show native word boxes" })).toBeNull();
  });

  it("shows overlapping-layer wording for near-overprint rejection", () => {
    const rejectedPage = {
      ...acceptedPage,
      decision: "rejected",
      source_mode: "visual_authority",
      provisional_native_text: null,
      words: [],
      trust: {
        ...acceptedPage.trust,
        reason_codes: ["excessive_near_overprint_duplicates", "native_text_rejected"],
        native_result_available: false,
        visual_processing_required: true,
      },
    } as NativePageResult;
    render(
      <NativeInspectionPanel
        summary={summary}
        page={rejectedPage}
        nativeOverlayEnabled={false}
        onToggleNativeOverlay={vi.fn()}
      />,
    );

    expect(
      screen.getByText(
        /overlapping native text layers that could not be trusted\. Visual processing is required/i,
      ),
    ).toBeInTheDocument();
  });

  it("renders canonical duplicate evidence without contradicting selected path", () => {
    const evidencePage = {
      ...acceptedPage,
      decision: "rejected",
      source_mode: "visual_authority",
      provisional_native_text: null,
      trust: {
        ...acceptedPage.trust,
        hard_rejection: true,
        duplicate_hard_rejection: true,
        reason_codes: ["excessive_near_overprint_duplicates"],
        metrics: {
          ...metrics,
          hard_rule_path: "B",
          duplicate_layer_evidence: {
            policy_version: "phase3-v1.6",
            strict_duplicate_ratio: 0,
            near_overprint_duplicate_ratio: 0.05,
            duplicate_layer_coverage_ratio: 1,
            matched_near_duplicate_count: 100,
            duplicate_line_count: 4,
            duplicate_region_count: 1,
            dominant_offset_x: 1,
            dominant_offset_y: 1,
            dominant_offset_support_ratio: 0.1,
            top_k_offset_cluster_support_ratio: 0.2,
            offset_cluster_count: 2,
            geometric_overlap_present: true,
            path_a_rules: [],
            path_b_rules: [
              {
                rule_id: "path_b_structure",
                metric_name: "duplicate_line_or_region_count",
                actual_value: "dup_lines=4;dup_regions=1",
                operator: "satisfies",
                threshold: "dup_lines>=2 OR dup_regions>=1",
                mandatory: true,
                passed: true,
                applies_to_path: "B",
                explanation: "structure",
              },
            ],
            path_a_satisfied: false,
            path_b_satisfied: true,
            selected_path: "B",
            hard_rejection: true,
          },
        },
        native_result_available: false,
        visual_processing_required: true,
      },
    } as NativePageResult;

    render(
      <NativeInspectionPanel
        summary={summary}
        page={evidencePage}
        nativeOverlayEnabled={false}
        onToggleNativeOverlay={vi.fn()}
      />,
    );

    expect(screen.getByTestId("duplicate-layer-evidence")).toBeInTheDocument();
    expect(screen.getByText(/Selected path: B/)).toBeInTheDocument();
    expect(screen.getByText(/Hard rejection caused by duplicate layer: Yes/)).toBeInTheDocument();
    expect(screen.getByTestId("dup-rule-path_b_structure").textContent).toMatch(/pass/);
    expect(screen.getByTestId("overall-native-hard-rejection").textContent).toMatch(/true/);
    expect(screen.getByTestId("duplicate-layer-hard-rejection").textContent).toMatch(/true/);
  });
});
