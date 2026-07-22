import { describe, expect, it } from "vitest";

import { VIEWER_MAX_SCALE, VIEWER_MIN_SCALE, VIEWER_SCALE_STEP } from "./constants";
import {
  clampScale,
  computeEffectivePageDimensions,
  computeFitPageScale,
  computeFitWidthScale,
  cycleRotation,
  dimensionsExceedTolerance,
  rotateNormalizedPoint,
  rotateNormalizedRect,
  scaleRectToPixels,
  stepScale,
  swapDimensionsForRotation,
} from "./geometry";

describe("rotateNormalizedPoint", () => {
  it("maps 0 degrees to (x, y)", () => {
    expect(rotateNormalizedPoint({ x: 0.2, y: 0.3 }, 0)).toEqual({ x: 0.2, y: 0.3 });
  });

  it("maps 90 degrees to (1 - y, x)", () => {
    expect(rotateNormalizedPoint({ x: 0.2, y: 0.3 }, 90)).toEqual({ x: 0.7, y: 0.2 });
  });

  it("maps 180 degrees to (1 - x, 1 - y)", () => {
    expect(rotateNormalizedPoint({ x: 0.2, y: 0.3 }, 180)).toEqual({ x: 0.8, y: 0.7 });
  });

  it("maps 270 degrees to (y, 1 - x)", () => {
    expect(rotateNormalizedPoint({ x: 0.2, y: 0.3 }, 270)).toEqual({ x: 0.3, y: 0.8 });
  });
});

describe("rotateNormalizedRect", () => {
  const rect = { x: 0.1, y: 0.15, width: 0.25, height: 0.1 };

  it("leaves the rect unchanged at 0 degrees", () => {
    const rotated = rotateNormalizedRect(rect, 0);
    expect(rotated.x).toBeCloseTo(0.1);
    expect(rotated.y).toBeCloseTo(0.15);
    expect(rotated.width).toBeCloseTo(0.25);
    expect(rotated.height).toBeCloseTo(0.1);
  });

  it("swaps width and height at 90 degrees", () => {
    const rotated = rotateNormalizedRect(rect, 90);
    expect(rotated.width).toBeCloseTo(0.1);
    expect(rotated.height).toBeCloseTo(0.25);
  });

  it("keeps dimensions but flips position at 180 degrees", () => {
    const rotated = rotateNormalizedRect(rect, 180);
    expect(rotated.width).toBeCloseTo(0.25);
    expect(rotated.height).toBeCloseTo(0.1);
    expect(rotated.x).toBeCloseTo(1 - 0.1 - 0.25);
    expect(rotated.y).toBeCloseTo(1 - 0.15 - 0.1);
  });

  it("swaps width and height at 270 degrees", () => {
    const rotated = rotateNormalizedRect(rect, 270);
    expect(rotated.width).toBeCloseTo(0.1);
    expect(rotated.height).toBeCloseTo(0.25);
  });
});

describe("scaleRectToPixels", () => {
  it("scales a normalised rect into pixel space", () => {
    const rect = { x: 0.1, y: 0.2, width: 0.3, height: 0.4 };
    expect(scaleRectToPixels(rect, 1000, 500)).toEqual({
      left: 100,
      top: 100,
      width: 300,
      height: 200,
    });
  });
});

describe("swapDimensionsForRotation / computeEffectivePageDimensions", () => {
  it("does not swap at 0 or 180 degrees", () => {
    expect(swapDimensionsForRotation(600, 800, 0)).toEqual({ width: 600, height: 800 });
    expect(swapDimensionsForRotation(600, 800, 180)).toEqual({ width: 600, height: 800 });
  });

  it("swaps at 90 or 270 degrees", () => {
    expect(swapDimensionsForRotation(600, 800, 90)).toEqual({ width: 800, height: 600 });
    expect(swapDimensionsForRotation(600, 800, 270)).toEqual({ width: 800, height: 600 });
  });

  it("accounts for intrinsic rotation when computing effective page size", () => {
    expect(computeEffectivePageDimensions(612, 792, 0)).toEqual({ width: 612, height: 792 });
    expect(computeEffectivePageDimensions(612, 792, 90)).toEqual({ width: 792, height: 612 });
  });
});

describe("dimensionsExceedTolerance", () => {
  it("is false within tolerance", () => {
    expect(dimensionsExceedTolerance(612, 792, 612.3, 791.8, 0.5)).toBe(false);
  });

  it("is true beyond tolerance on width", () => {
    expect(dimensionsExceedTolerance(612, 792, 613, 792, 0.5)).toBe(true);
  });

  it("is true beyond tolerance on height", () => {
    expect(dimensionsExceedTolerance(612, 792, 612, 793, 0.5)).toBe(true);
  });
});

describe("computeFitWidthScale", () => {
  it("fits the unrotated page width to the container", () => {
    // 612pt-wide page in a 1224px-wide container -> scale 2.
    expect(computeFitWidthScale(1224, 612, 792, 0)).toBeCloseTo(2);
  });

  it("uses the rotated (swapped) width at 90/270 degrees", () => {
    // At 90 degrees the visual width becomes the page's height (792pt).
    expect(computeFitWidthScale(792, 612, 792, 90)).toBeCloseTo(1);
  });

  it("clamps to VIEWER_MIN_SCALE/VIEWER_MAX_SCALE", () => {
    expect(computeFitWidthScale(1, 612, 792, 0)).toBe(VIEWER_MIN_SCALE);
    expect(computeFitWidthScale(100_000, 612, 792, 0)).toBe(VIEWER_MAX_SCALE);
  });

  it("falls back to the minimum scale for degenerate input", () => {
    expect(computeFitWidthScale(0, 612, 792, 0)).toBe(VIEWER_MIN_SCALE);
    expect(computeFitWidthScale(1000, 0, 792, 0)).toBe(VIEWER_MIN_SCALE);
  });
});

describe("computeFitPageScale", () => {
  it("fits the smaller of width/height so the whole page is visible", () => {
    // Page 612x792 in an 1224x792 container: width ratio 2, height ratio 1 -> min is 1.
    expect(computeFitPageScale(1224, 792, 612, 792, 0)).toBeCloseTo(1);
  });

  it("uses rotated dimensions at 90/270 degrees", () => {
    // Rotated 90: effective page becomes 792x612. Container 792x1224 ->
    // width ratio 1, height ratio 2 -> min is 1.
    expect(computeFitPageScale(792, 1224, 612, 792, 90)).toBeCloseTo(1);
  });

  it("clamps to the supported scale range", () => {
    expect(computeFitPageScale(1, 1, 612, 792, 0)).toBe(VIEWER_MIN_SCALE);
    expect(computeFitPageScale(100_000, 100_000, 612, 792, 0)).toBe(VIEWER_MAX_SCALE);
  });
});

describe("clampScale", () => {
  it("passes through values already within range", () => {
    expect(clampScale(1)).toBe(1);
    expect(clampScale(2.5)).toBe(2.5);
  });

  it("clamps below VIEWER_MIN_SCALE", () => {
    expect(clampScale(0.01)).toBe(VIEWER_MIN_SCALE);
    expect(clampScale(-5)).toBe(VIEWER_MIN_SCALE);
  });

  it("clamps above VIEWER_MAX_SCALE", () => {
    expect(clampScale(10)).toBe(VIEWER_MAX_SCALE);
  });

  it("treats non-finite input as the minimum scale", () => {
    expect(clampScale(Number.NaN)).toBe(VIEWER_MIN_SCALE);
    expect(clampScale(Number.POSITIVE_INFINITY)).toBe(VIEWER_MIN_SCALE);
  });
});

describe("stepScale", () => {
  it("steps up and clamps at the maximum", () => {
    expect(stepScale(1, VIEWER_SCALE_STEP, 1)).toBeCloseTo(1 + VIEWER_SCALE_STEP);
    expect(stepScale(VIEWER_MAX_SCALE, VIEWER_SCALE_STEP, 1)).toBe(VIEWER_MAX_SCALE);
  });

  it("steps down and clamps at the minimum", () => {
    expect(stepScale(1, VIEWER_SCALE_STEP, -1)).toBeCloseTo(1 - VIEWER_SCALE_STEP);
    expect(stepScale(VIEWER_MIN_SCALE, VIEWER_SCALE_STEP, -1)).toBe(VIEWER_MIN_SCALE);
  });
});

describe("cycleRotation", () => {
  it("cycles clockwise through 0 -> 90 -> 180 -> 270 -> 0", () => {
    expect(cycleRotation(0, 1)).toBe(90);
    expect(cycleRotation(90, 1)).toBe(180);
    expect(cycleRotation(180, 1)).toBe(270);
    expect(cycleRotation(270, 1)).toBe(0);
  });

  it("cycles counter-clockwise through 0 -> 270 -> 180 -> 90 -> 0", () => {
    expect(cycleRotation(0, -1)).toBe(270);
    expect(cycleRotation(270, -1)).toBe(180);
    expect(cycleRotation(180, -1)).toBe(90);
    expect(cycleRotation(90, -1)).toBe(0);
  });
});
