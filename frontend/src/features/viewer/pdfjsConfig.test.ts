import { describe, expect, it, vi } from "vitest";

import { __testables } from "./PdfCanvas";
import {
  buildGetDocumentOptions,
  canvasLooksBlank,
  getPdfjsWasmUrl,
  isAlignmentOverlayAvailable,
  isPdfjsIsolationMode,
  isRenderingCancelledError,
  resolveDevicePixelRatio,
} from "./pdfjsConfig";

describe("getPdfjsWasmUrl", () => {
  it("points at the unhashed /pdfjs-wasm/ directory with a trailing slash", () => {
    expect(getPdfjsWasmUrl()).toMatch(/pdfjs-wasm\/$/);
  });
});

describe("buildGetDocumentOptions", () => {
  it("returns url + wasmUrl by default (range enabled)", () => {
    vi.stubEnv("VITE_PDFJS_ISOLATION_MODE", "");
    const options = buildGetDocumentOptions("http://example.test/doc.pdf");
    expect(options.url).toBe("http://example.test/doc.pdf");
    expect(options.wasmUrl).toMatch(/\/$/);
    expect(options.disableRange).toBeUndefined();
    expect(isPdfjsIsolationMode()).toBe(false);
  });

  it("disables range/stream/autoFetch in isolation mode", () => {
    vi.stubEnv("VITE_PDFJS_ISOLATION_MODE", "true");
    const options = buildGetDocumentOptions("http://example.test/doc.pdf");
    expect(options).toMatchObject({
      url: "http://example.test/doc.pdf",
      disableRange: true,
      disableStream: true,
      disableAutoFetch: true,
    });
    expect(options.wasmUrl).toMatch(/\/$/);
    expect(isPdfjsIsolationMode()).toBe(true);
  });
});

describe("resolveDevicePixelRatio", () => {
  it("caps DPR when VITE_PDFJS_MAX_DPR is set", () => {
    vi.stubEnv("VITE_PDFJS_MAX_DPR", "1");
    expect(resolveDevicePixelRatio(2.5)).toBe(1);
  });

  it("passes through finite positive DPR when uncapped", () => {
    vi.stubEnv("VITE_PDFJS_MAX_DPR", "");
    expect(resolveDevicePixelRatio(2)).toBe(2);
  });
});

describe("isRenderingCancelledError", () => {
  it("recognises RenderingCancelledException", () => {
    expect(isRenderingCancelledError({ name: "RenderingCancelledException", message: "x" })).toBe(
      true,
    );
  });

  it("does not treat generic errors as cancelled", () => {
    expect(isRenderingCancelledError(new Error("boom"))).toBe(false);
  });
});

describe("cancelRenderTask", () => {
  it("awaits the prior task promise before resolving", async () => {
    let settled = false;
    const task = {
      cancel: vi.fn(),
      promise: new Promise<void>((resolve) => {
        queueMicrotask(() => {
          settled = true;
          resolve();
        });
      }),
    };
    await __testables.cancelRenderTask(task as never);
    expect(task.cancel).toHaveBeenCalledOnce();
    expect(settled).toBe(true);
  });

  it("swallows RenderingCancelledException from the awaited promise", async () => {
    const task = {
      cancel: vi.fn(),
      promise: Promise.reject({ name: "RenderingCancelledException", message: "cancelled" }),
    };
    await expect(__testables.cancelRenderTask(task as never)).resolves.toBeUndefined();
  });
});

describe("canvasLooksBlank", () => {
  it("treats missing 2d context as blank", () => {
    const canvas = {
      width: 40,
      height: 40,
      getContext: () => null,
    } as unknown as HTMLCanvasElement;
    expect(canvasLooksBlank(canvas)).toBe(true);
  });

  it("reports blank when every sampled pixel is near-white", () => {
    const white = new Uint8ClampedArray(40 * 40 * 4);
    for (let i = 0; i < white.length; i += 4) {
      white[i] = 255;
      white[i + 1] = 255;
      white[i + 2] = 255;
      white[i + 3] = 255;
    }
    const canvas = {
      width: 40,
      height: 40,
      getContext: () => ({
        getImageData: () => ({ data: white }),
      }),
    } as unknown as HTMLCanvasElement;
    expect(canvasLooksBlank(canvas)).toBe(true);
  });

  it("reports nonblank when dark pixels are present", () => {
    const pixels = new Uint8ClampedArray(40 * 40 * 4);
    for (let i = 0; i < pixels.length; i += 4) {
      pixels[i] = 255;
      pixels[i + 1] = 255;
      pixels[i + 2] = 255;
      pixels[i + 3] = 255;
    }
    // Paint a dark block so multiple sample points hit ink.
    for (let y = 0; y < 24; y += 1) {
      for (let x = 0; x < 24; x += 1) {
        const index = (y * 40 + x) * 4;
        pixels[index] = 10;
        pixels[index + 1] = 10;
        pixels[index + 2] = 10;
      }
    }
    const canvas = {
      width: 40,
      height: 40,
      getContext: () => ({
        getImageData: () => ({ data: pixels }),
      }),
    } as unknown as HTMLCanvasElement;
    expect(canvasLooksBlank(canvas)).toBe(false);
  });
});

describe("isAlignmentOverlayAvailable", () => {
  it("is false unless DEV and the overlay env flag are set", () => {
    vi.stubEnv("VITE_SHOW_ALIGNMENT_OVERLAY", "");
    // In Vitest, import.meta.env.DEV is typically true; the flag still gates.
    expect(isAlignmentOverlayAvailable()).toBe(false);
    vi.stubEnv("VITE_SHOW_ALIGNMENT_OVERLAY", "true");
    expect(isAlignmentOverlayAvailable()).toBe(true);
  });
});
