import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { OcrConfidenceBadge } from "./OcrConfidenceBadge";

describe("OcrConfidenceBadge", () => {
  it("shows recognition confidence separately from quality status", () => {
    render(
      <OcrConfidenceBadge
        score={0.82}
        qualityStatus="usable_with_warnings"
        fallbackUsed
        selectedPass="fallback"
        primaryLimitSide={960}
        fallbackLimitSide={1600}
        lowConfidenceCount={3}
      />,
    );
    expect(screen.getByText(/OCR recognition conf 0\.82/)).toBeInTheDocument();
    expect(screen.getByTestId("ocr-quality-status")).toHaveTextContent("usable_with_warnings");
    expect(screen.getByTestId("ocr-fallback-used")).toBeInTheDocument();
    expect(screen.getByTestId("ocr-pass-labels")).toHaveTextContent("Primary pass: 960");
    expect(screen.getByTestId("ocr-pass-labels")).toHaveTextContent("Fallback pass: 1600");
    expect(screen.getByTestId("ocr-pass-labels")).toHaveTextContent("Selected pass: Fallback");
  });

  it("does not claim recognition confidence is transcript accuracy", () => {
    render(<OcrConfidenceBadge score={0.9} qualityStatus="good" />);
    expect(screen.queryByText(/accuracy/i)).not.toBeInTheDocument();
    expect(screen.getByText(/OCR recognition conf/)).toBeInTheDocument();
  });
});
