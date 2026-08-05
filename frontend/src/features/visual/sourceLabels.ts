/** Exact source labels keyed by page_result_state / source_mode. */

export const PAGE_RESULT_SOURCE_LABELS = {
  digital_native: "Native PDF text",
  embedded_ocr_verified: "Verified embedded OCR",
  embedded_ocr_targeted_repair: "Verified embedded OCR with visual repair",
  full_visual_ocr: "Printed visual OCR",
  visual_no_text: "No meaningful text detected",
  vision_reserved_pending_phase_6: "Reserved for vision processing",
  page_failed: "Page processing failed",
  pending: "Processing",
  cancelled: "Cancelled",
} as const;

export type PageResultStateKey = keyof typeof PAGE_RESULT_SOURCE_LABELS;

export function sourceLabelForPage(page: {
  source_label?: string | null;
  page_result_state?: string | null;
  source_mode?: string | null;
  page_route?: string | null;
}): string {
  if (page.source_label) {
    return page.source_label;
  }
  const state = page.page_result_state ?? page.page_route;
  if (state && state in PAGE_RESULT_SOURCE_LABELS) {
    return PAGE_RESULT_SOURCE_LABELS[state as PageResultStateKey];
  }
  if (page.source_mode === "native_authority") {
    return PAGE_RESULT_SOURCE_LABELS.digital_native;
  }
  if (page.source_mode === "embedded_ocr_authority") {
    return PAGE_RESULT_SOURCE_LABELS.embedded_ocr_verified;
  }
  return PAGE_RESULT_SOURCE_LABELS.full_visual_ocr;
}

export function overlaySourceKind(page: {
  overlay_source?: string | null;
  source_mode?: string | null;
  page_result_state?: string | null;
}): "verified_embedded_ocr_word" | "printed_visual_ocr_word" | "targeted_repair_word" {
  if (page.overlay_source === "verified_embedded_ocr_word") {
    return "verified_embedded_ocr_word";
  }
  if (page.overlay_source === "targeted_repair_word") {
    return "targeted_repair_word";
  }
  if (
    page.source_mode === "embedded_ocr_authority" ||
    page.page_result_state === "embedded_ocr_verified" ||
    page.page_result_state === "embedded_ocr_targeted_repair"
  ) {
    return "verified_embedded_ocr_word";
  }
  return "printed_visual_ocr_word";
}
