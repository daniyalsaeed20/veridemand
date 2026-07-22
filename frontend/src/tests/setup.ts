import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});

// jsdom does not implement the Canvas 2D API (`DOMMatrix`, `Path2D`). Real PDF
// rendering only ever happens in a browser, but `pdfjs-dist` references
// `DOMMatrix` at *module load* time (a top-level `new DOMMatrix()` constant),
// so merely importing the viewer feature in a jsdom test would otherwise
// throw before any test body runs. These are intentionally minimal,
// non-functional stubs — no test in this suite renders real pixels onto a
// <canvas>.
class DOMMatrixPolyfill {
  constructor() {}
  translate(): this {
    return this;
  }
  scale(): this {
    return this;
  }
  multiplySelf(): this {
    return this;
  }
  preMultiplySelf(): this {
    return this;
  }
  invertSelf(): this {
    return this;
  }
}

if (typeof globalThis.DOMMatrix === "undefined") {
  Object.defineProperty(globalThis, "DOMMatrix", { value: DOMMatrixPolyfill, configurable: true });
}

class Path2DPolyfill {
  addPath(): void {}
}

if (typeof globalThis.Path2D === "undefined") {
  Object.defineProperty(globalThis, "Path2D", { value: Path2DPolyfill, configurable: true });
}
