// Pure geometry helpers for the canonical viewer (Phase 2).
//
// All normalised coordinates use a top-left origin, x left->right, y
// top->bottom, values in [0, 1] — matching
// `docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md` and
// `backend/app/contracts/geometry.py`. Backend geometry already has the PDF's
// intrinsic page rotation baked in; the transforms below apply only the
// additional client-side (viewer) rotation chosen by the user.
//
// Kept dependency-free and side-effect-free so it can be unit tested without a
// DOM, canvas, or PDF.js instance.

import { VIEWER_MAX_SCALE, VIEWER_MIN_SCALE, type RotationDegrees } from "./constants";

export interface NormalizedPoint {
  readonly x: number;
  readonly y: number;
}

export interface NormalizedRect {
  readonly x: number;
  readonly y: number;
  readonly width: number;
  readonly height: number;
}

export interface PixelRect {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

/**
 * Rotate a single normalised point by a viewer rotation of 0/90/180/270
 * degrees (clockwise), matching:
 *   0:   (x, y)
 *   90:  (1 - y, x)
 *   180: (1 - x, 1 - y)
 *   270: (y, 1 - x)
 */
export function rotateNormalizedPoint(
  point: NormalizedPoint,
  rotation: RotationDegrees,
): NormalizedPoint {
  switch (rotation) {
    case 0:
      return { x: point.x, y: point.y };
    case 90:
      return { x: 1 - point.y, y: point.x };
    case 180:
      return { x: 1 - point.x, y: 1 - point.y };
    case 270:
      return { x: point.y, y: 1 - point.x };
    default:
      return point;
  }
}

// Rotates every corner of an axis-aligned normalised rectangle and returns the
// resulting axis-aligned rectangle. Because rotation is always a multiple of
// 90 degrees, the rotated shape remains axis-aligned.
export function rotateNormalizedRect(
  rect: NormalizedRect,
  rotation: RotationDegrees,
): NormalizedRect {
  const corners: NormalizedPoint[] = [
    { x: rect.x, y: rect.y },
    { x: rect.x + rect.width, y: rect.y },
    { x: rect.x + rect.width, y: rect.y + rect.height },
    { x: rect.x, y: rect.y + rect.height },
  ].map((corner) => rotateNormalizedPoint(corner, rotation));

  const xs = corners.map((corner) => corner.x);
  const ys = corners.map((corner) => corner.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const maxX = Math.max(...xs);
  const maxY = Math.max(...ys);

  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

// Scales a normalised (0..1) rectangle into device-independent pixel space for
// a rendered page of the given pixel dimensions.
export function scaleRectToPixels(
  rect: NormalizedRect,
  pixelWidth: number,
  pixelHeight: number,
): PixelRect {
  return {
    left: rect.x * pixelWidth,
    top: rect.y * pixelHeight,
    width: rect.width * pixelWidth,
    height: rect.height * pixelHeight,
  };
}

// A 90/270 degree rotation swaps the visual width and height of a page; 0/180
// do not.
export function swapDimensionsForRotation(
  width: number,
  height: number,
  rotation: RotationDegrees,
): { width: number; height: number } {
  return rotation === 90 || rotation === 270 ? { width: height, height: width } : { width, height };
}

/**
 * Computes the "effective" (as-displayed) dimensions of a page given its raw,
 * unrotated size and an intrinsic rotation reported by PDF.js (`page.rotate`,
 * one of 0/90/180/270). This mirrors how the backend computes
 * `width_points`/`height_points` on `CanonicalPageMetadata`, so the two can be
 * compared directly for the dimension-tolerance check below.
 */
export function computeEffectivePageDimensions(
  rawWidthPoints: number,
  rawHeightPoints: number,
  intrinsicRotation: RotationDegrees,
): { width: number; height: number } {
  return swapDimensionsForRotation(rawWidthPoints, rawHeightPoints, intrinsicRotation);
}

// True when the PDF.js-reported effective page size disagrees with the
// backend canonical metadata beyond the allowed tolerance (in PDF points).
export function dimensionsExceedTolerance(
  effectiveWidthPoints: number,
  effectiveHeightPoints: number,
  backendWidthPoints: number,
  backendHeightPoints: number,
  tolerancePoints: number,
): boolean {
  return (
    Math.abs(effectiveWidthPoints - backendWidthPoints) > tolerancePoints ||
    Math.abs(effectiveHeightPoints - backendHeightPoints) > tolerancePoints
  );
}

// Scale that makes the (viewer-rotated) page exactly fill the container width.
export function computeFitWidthScale(
  containerWidthPx: number,
  pageWidthPoints: number,
  pageHeightPoints: number,
  rotation: RotationDegrees,
): number {
  const { width } = swapDimensionsForRotation(pageWidthPoints, pageHeightPoints, rotation);
  if (!(containerWidthPx > 0) || !(width > 0)) {
    return VIEWER_MIN_SCALE;
  }
  return clampScale(containerWidthPx / width);
}

// Scale that makes the (viewer-rotated) page fully visible within the
// container (both width and height fit, without cropping).
export function computeFitPageScale(
  containerWidthPx: number,
  containerHeightPx: number,
  pageWidthPoints: number,
  pageHeightPoints: number,
  rotation: RotationDegrees,
): number {
  const { width, height } = swapDimensionsForRotation(pageWidthPoints, pageHeightPoints, rotation);
  if (!(containerWidthPx > 0) || !(containerHeightPx > 0) || !(width > 0) || !(height > 0)) {
    return VIEWER_MIN_SCALE;
  }
  return clampScale(Math.min(containerWidthPx / width, containerHeightPx / height));
}

// Clamps a manual/computed scale into the supported viewer range
// [VIEWER_MIN_SCALE, VIEWER_MAX_SCALE].
export function clampScale(scale: number): number {
  if (!Number.isFinite(scale)) {
    return VIEWER_MIN_SCALE;
  }
  return Math.min(VIEWER_MAX_SCALE, Math.max(VIEWER_MIN_SCALE, scale));
}

// Rounds a scale to the nearest step (used when nudging manual zoom in/out) and
// clamps the result.
export function stepScale(currentScale: number, step: number, direction: 1 | -1): number {
  return clampScale(currentScale + step * direction);
}

// Cycles a rotation value clockwise (+1) or counter-clockwise (-1) in 90
// degree increments, wrapping at the ends.
export function cycleRotation(current: RotationDegrees, direction: 1 | -1): RotationDegrees {
  const steps: RotationDegrees[] = [0, 90, 180, 270];
  const index = steps.indexOf(current);
  const nextIndex = (index + direction + steps.length) % steps.length;
  return steps[nextIndex];
}
