import { describe, expect, it } from "vitest";

import { overlaySourceKind, sourceLabelForPage } from "./sourceLabels";

describe("sourceLabels", () => {
  it("maps page_result_state to exact labels", () => {
    expect(sourceLabelForPage({ page_result_state: "embedded_ocr_verified" })).toBe(
      "Verified embedded OCR",
    );
    expect(sourceLabelForPage({ page_result_state: "full_visual_ocr" })).toBe("Printed visual OCR");
    expect(sourceLabelForPage({ source_mode: "native_authority" })).toBe("Native PDF text");
  });

  it("prefers explicit source_label", () => {
    expect(
      sourceLabelForPage({
        source_label: "Verified embedded OCR with visual repair",
        page_result_state: "full_visual_ocr",
      }),
    ).toBe("Verified embedded OCR with visual repair");
  });

  it("selects overlay kind for embedded authority", () => {
    expect(overlaySourceKind({ source_mode: "embedded_ocr_authority" })).toBe(
      "verified_embedded_ocr_word",
    );
    expect(overlaySourceKind({ source_mode: "visual_authority" })).toBe("printed_visual_ocr_word");
  });
});
