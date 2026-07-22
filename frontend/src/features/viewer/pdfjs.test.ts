import { describe, expect, it } from "vitest";

import { GlobalWorkerOptions } from "pdfjs-dist";

import { PDFJS_WORKER_SRC } from "./pdfjs";

describe("pdfjs worker bootstrap", () => {
  it("resolves the worker script from a local build asset, never a CDN", () => {
    // Never point at mozilla's/unpkg's/cdnjs's hosted worker scripts.
    expect(PDFJS_WORKER_SRC).not.toMatch(/^https?:\/\//i);
    expect(PDFJS_WORKER_SRC).not.toMatch(/cdn|unpkg|jsdelivr|mozilla\.github\.io/i);
  });

  it("resolves to the pdf.js worker build artifact", () => {
    expect(PDFJS_WORKER_SRC).toMatch(/pdf\.worker(\.min)?\.mjs/);
  });

  it("configures pdfjs-dist's GlobalWorkerOptions with the same local URL", () => {
    expect(GlobalWorkerOptions.workerSrc).toBe(PDFJS_WORKER_SRC);
  });
});
