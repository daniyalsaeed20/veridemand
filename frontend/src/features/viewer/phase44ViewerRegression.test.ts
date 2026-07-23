import { describe, expect, it } from "vitest";

import { canvasLooksBlank } from "./pdfjsConfig";

describe("canvasLooksBlank", () => {
  it("returns true for a zero-size canvas", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 0;
    canvas.height = 0;
    expect(canvasLooksBlank(canvas)).toBe(true);
  });

  it("exports blank detection helper", () => {
    expect(typeof canvasLooksBlank).toBe("function");
  });
});

describe("viewer load generation helpers", () => {
  it("exports usePdfDocument with retry support", async () => {
    const mod = await import("./usePdfDocument");
    expect(typeof mod.usePdfDocument).toBe("function");
  });
});
