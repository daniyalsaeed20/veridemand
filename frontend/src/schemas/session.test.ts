import { describe, expect, it } from "vitest";
import { DocumentUploadBatchSchema, DocumentSchema } from "./documents";
import { CaseSessionSchema } from "./session";

describe("session contract validation", () => {
  it("accepts a valid CaseSession payload", () => {
    const parsed = CaseSessionSchema.safeParse({
      id: "ses_01JEXAMPLE000000000000000",
      created_at: "2026-07-18T12:00:00Z",
      expires_at: "2026-07-18T14:00:00Z",
      last_activity_at: "2026-07-18T12:00:00Z",
      status: "created",
      settings: { ocr_render_dpi: 200 },
      warning: "Temporary session warning",
    });
    expect(parsed.success).toBe(true);
  });

  it("rejects missing ses_ prefix", () => {
    const parsed = CaseSessionSchema.safeParse({
      id: "bad",
      created_at: "2026-07-18T12:00:00Z",
      expires_at: "2026-07-18T14:00:00Z",
      last_activity_at: "2026-07-18T12:00:00Z",
      status: "created",
    });
    expect(parsed.success).toBe(false);
  });
});

describe("upload batch contract validation", () => {
  const doc = {
    id: "doc_01JEXAMPLE000000000000001",
    session_id: "ses_01JEXAMPLE000000000000000",
    display_name: "police-report.pdf",
    file_type: "pdf",
    content_sha256: "a".repeat(64),
    page_count: 1,
    classification: null,
    status: "uploaded",
    exclude_from_drafting: false,
    treat_as_secondary_evidence: false,
  };

  it("accepts accepted and rejected lists", () => {
    const parsed = DocumentUploadBatchSchema.safeParse({
      accepted: [doc],
      rejected: [
        {
          display_name: "notes.exe",
          error_code: "upload_unsupported_type",
          message: "This file type is not supported in the prototype.",
        },
      ],
    });
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.accepted).toHaveLength(1);
      expect(parsed.data.rejected[0]?.error_code).toBe("upload_unsupported_type");
    }
  });

  it("validates document status fields for UI accepted/rejected states", () => {
    const uploaded = DocumentSchema.safeParse(doc);
    expect(uploaded.success).toBe(true);
    const duplicate = DocumentSchema.safeParse({ ...doc, status: "duplicate" });
    expect(duplicate.success).toBe(true);
  });
});
