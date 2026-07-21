import { describe, expect, it } from "vitest";
import { HealthResponseSchema } from "./health";
import fixture from "../fixtures/health-ok.json";

describe("HealthResponseSchema", () => {
  it("validates the synthetic health fixture", () => {
    const parsed = HealthResponseSchema.safeParse(fixture);
    expect(parsed.success).toBe(true);
    if (parsed.success) {
      expect(parsed.data.contracts_version).toBe("0.1");
      expect(parsed.data.status).toBe("ok");
    }
  });

  it("rejects a payload missing contracts_version", () => {
    const parsed = HealthResponseSchema.safeParse({
      status: "ok",
      api_version: "v1",
      time_utc: "2026-07-21T12:00:00Z",
    });
    expect(parsed.success).toBe(false);
  });
});
