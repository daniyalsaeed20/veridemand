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

  it("maps repaired page state to visual repair label", () => {
    expect(sourceLabelForPage({ page_result_state: "embedded_ocr_targeted_repair" })).toBe(
      "Verified embedded OCR with visual repair",
    );
    expect(
      overlaySourceKind({
        page_result_state: "embedded_ocr_targeted_repair",
        overlay_source: "targeted_repair_word",
      }),
    ).toBe("targeted_repair_word");
  });
});
