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

    expect(screen.getByText(/Document source policy: mixed_authority/)).toBeInTheDocument();
    expect(screen.getByText("Visual agreement not yet evaluated.")).toBeInTheDocument();
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
});
