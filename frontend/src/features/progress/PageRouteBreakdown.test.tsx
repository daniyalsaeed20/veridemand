import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageRouteBreakdown } from "./PageRouteBreakdown";

describe("PageRouteBreakdown", () => {
  it("displays exclusive counts from final_route_histogram only (not subtraction)", () => {
    // Trap: retained - embedded = 15, but canonical exclusive digital_native is 3.
    render(
      <PageRouteBreakdown
        snapshot={{
          document_pages_total: 104,
          native_pages_retained: 20,
          embedded_ocr_pages_verified: 5,
          full_ocr_pages_selected: 87,
          full_ocr_pages_completed: 13,
          full_ocr_pages_remaining: 74,
          final_route_histogram: {
            digital_native_pages: 3,
            embedded_ocr_verified_pages: 5,
            embedded_ocr_targeted_repair_pages: 0,
            full_visual_ocr_pages: 87,
            visual_no_text_pages: 1,
            page_failed_pages: 0,
            page_cancelled_pages: 0,
            pending_pages: 8,
          },
        }}
      />,
    );
    expect(screen.getByText(/Exclusive route histogram/i)).toBeInTheDocument();
    expect(screen.getByText(/Digital native:/i).textContent).toMatch(/:\s*3\b/);
    expect(screen.getByText(/Digital native:/i).textContent).not.toMatch(/:\s*15\b/);
    expect(screen.getByText(/Exclusive sum:/i).textContent).toMatch(/104/);
    expect(screen.getByText(/matches/i)).toBeInTheDocument();
    expect(screen.getByText(/Native pages retained \(includes embedded\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Selection diagnostics \(overlapping\)/i)).toBeInTheDocument();
  });

  it("shows skeletons when final_route_histogram is absent", () => {
    render(
      <PageRouteBreakdown
        snapshot={{
          document_pages_total: 104,
          native_pages_retained: 17,
          embedded_ocr_pages_verified: 17,
          full_ocr_pages_selected: 87,
        }}
      />,
    );
    expect(screen.getByText(/Exclusive route histogram/i)).toBeInTheDocument();
    expect(screen.getByText(/Digital native:/i).textContent).not.toMatch(/:\s*0\b/);
    expect(
      screen.getByLabelText(/Page route breakdown/i).querySelectorAll(".MuiSkeleton-root").length,
    ).toBeGreaterThan(0);
  });
});
