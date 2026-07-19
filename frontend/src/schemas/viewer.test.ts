import { describe, expect, it } from "vitest";
import { DocumentPageSchema, ProcessEventSchema, SourceSpanSchema } from "./viewer";

describe("viewer schemas", () => {
  it("accepts a DocumentPage", () => {
    const parsed = DocumentPageSchema.safeParse({
      id: "page_doc_x_1",
      document_id: "doc_abc",
      page_number: 1,
      width: 612,
      height: 792,
      text_coverage: 0.1,
      route: "native",
      ocr_status: "not_needed",
      extraction_method: "native",
      quality_flags: [],
      token_count: 2,
      span_count: 1,
    });
    expect(parsed.success).toBe(true);
  });

  it("accepts a ProcessEvent", () => {
    const parsed = ProcessEventSchema.safeParse({
      sequence: 1,
      event: "process.completed",
      session_id: "ses_abc",
      document_id: null,
      page_number: null,
      status: "completed",
      message: "done",
      progress: 1,
      error_code: null,
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects span without polygons", () => {
    const parsed = SourceSpanSchema.safeParse({
      id: "span_abc",
      document_id: "doc_abc",
      page_number: 1,
      text: "x",
      token_ids: [],
      polygons: [],
      method: "native",
      confidence: 1,
    });
    expect(parsed.success).toBe(false);
  });
});
