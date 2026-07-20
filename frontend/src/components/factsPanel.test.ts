import { describe, expect, it } from "vitest";
import { FactSchema } from "../schemas/generated/Fact";

function categoryOf(factType: string): string {
  const i = factType.indexOf(".");
  return i === -1 ? "other" : factType.slice(0, i);
}

describe("Facts panel helpers", () => {
  it("groups fact types by category prefix", () => {
    expect(categoryOf("claim.number")).toBe("claim");
    expect(categoryOf("collision.date")).toBe("collision");
    expect(categoryOf("calc.visit_count")).toBe("calc");
  });

  it("validates generated Fact schema for Phase 5 fields", () => {
    const parsed = FactSchema.safeParse({
      id: "fact_01TESTFACT000000000000001",
      session_id: "ses_01TESTSESSION000000000001",
      fact_type: "claim.number",
      raw_value: "CLM-001",
      normalized_value: "CLM-001",
      display_value: "CLM-001",
      confidence: 0.9,
      status: "suggested",
      source_span_ids: ["span_01TESTSPAN00000000000001"],
      extraction_methods: ["context_parser"],
      provenance: "deterministic",
      criticality: "critical",
    });
    expect(parsed.success).toBe(true);
  });

  it("distinguishes fact status from OCR-style confidence numbers", () => {
    const fact = FactSchema.parse({
      id: "fact_01TESTFACT000000000000002",
      session_id: "ses_01TESTSESSION000000000001",
      fact_type: "collision.date",
      raw_value: "01/15/2024",
      normalized_value: "2024-01-15",
      confidence: 0.55,
      status: "needs_review",
      source_span_ids: ["span_01TESTSPAN00000000000002"],
      extraction_methods: ["context_parser"],
      description: "classification:ambiguous",
      provenance: "deterministic",
      criticality: "critical",
    });
    expect(fact.status).toBe("needs_review");
    expect(fact.confidence).toBe(0.55);
    expect(String(fact.description)).toContain("ambiguous");
  });
});
