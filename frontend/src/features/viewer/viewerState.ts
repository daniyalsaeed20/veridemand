// Ephemeral viewer UI state (Phase 2).
//
// Zustand store for viewer-only interaction state: which document/page is
// selected, zoom mode/scale, viewer-applied rotation and the overlay toggle.
// This is *never* persisted (no localStorage/IndexedDB/cookies) and never
// holds PDF bytes, canonical metadata, or any other server state — that all
// lives in the TanStack Query cache (`useCanonicalDocument`, `usePdfDocument`,
// `usePdfPage`). Losing this state on refresh is intentional and safe.

import { create } from "zustand";

import { clampScale, cycleRotation, stepScale } from "./geometry";
import { VIEWER_SCALE_STEP, type RotationDegrees, type ZoomMode } from "./constants";

const DEFAULT_ZOOM_MODE: ZoomMode = "fit_width";
const DEFAULT_ROTATION: RotationDegrees = 0;
const DEFAULT_MANUAL_SCALE = 1;

export interface ViewerState {
  readonly selectedDocumentId: string | null;
  readonly pageNumber: number;
  readonly zoomMode: ZoomMode;
  readonly manualScale: number;
  readonly userRotation: RotationDegrees;
  readonly overlayEnabled: boolean;
  readonly nativeOverlayEnabled: boolean;
  readonly ocrLineOverlayEnabled: boolean;
  readonly ocrWordOverlayEnabled: boolean;

  // Selects a document for viewing, resetting every other viewer field to its
  // default (page 1, no rotation, fit-width zoom, overlay off). Passing
  // `null` clears the selection (returns to the empty state).
  readonly selectDocument: (documentId: string | null) => void;
  readonly setPageNumber: (pageNumber: number) => void;
  readonly setZoomMode: (mode: ZoomMode) => void;
  readonly setManualScale: (scale: number) => void;
  // `currentEffectiveScale`, when provided, seeds the new manual scale from
  // whatever is actually on screen right now (which may come from a fit
  // mode), so switching to manual zoom feels continuous instead of jumping to
  // a stale remembered manual scale.
  readonly zoomIn: (currentEffectiveScale?: number) => void;
  readonly zoomOut: (currentEffectiveScale?: number) => void;
  readonly rotateClockwise: () => void;
  readonly rotateCounterClockwise: () => void;
  readonly setOverlayEnabled: (enabled: boolean) => void;
  readonly toggleOverlay: () => void;
  readonly toggleNativeOverlay: () => void;
  readonly toggleOcrLineOverlay: () => void;
  readonly toggleOcrWordOverlay: () => void;
  // Resets every field to the defaults used on a fresh document selection,
  // keeping the current selection. Used e.g. when the session itself resets.
  readonly reset: () => void;
}

const DEFAULTS = {
  pageNumber: 1,
  zoomMode: DEFAULT_ZOOM_MODE,
  manualScale: DEFAULT_MANUAL_SCALE,
  userRotation: DEFAULT_ROTATION,
  // Synthetic alignment overlay is off in normal user mode.
  overlayEnabled: false,
  nativeOverlayEnabled: false,
  ocrLineOverlayEnabled: false,
  ocrWordOverlayEnabled: false,
} as const;

export const useViewerStore = create<ViewerState>((set, get) => ({
  selectedDocumentId: null,
  ...DEFAULTS,

  selectDocument: (documentId) =>
    set({
      selectedDocumentId: documentId,
      ...DEFAULTS,
    }),

  setPageNumber: (pageNumber) => set({ pageNumber: Math.max(1, Math.trunc(pageNumber)) }),

  setZoomMode: (mode) => set({ zoomMode: mode }),

  setManualScale: (scale) => set({ zoomMode: "manual", manualScale: clampScale(scale) }),

  zoomIn: (currentEffectiveScale) =>
    set((state) => ({
      zoomMode: "manual",
      manualScale: stepScale(currentEffectiveScale ?? state.manualScale, VIEWER_SCALE_STEP, 1),
    })),

  zoomOut: (currentEffectiveScale) =>
    set((state) => ({
      zoomMode: "manual",
      manualScale: stepScale(currentEffectiveScale ?? state.manualScale, VIEWER_SCALE_STEP, -1),
    })),

  rotateClockwise: () => set((state) => ({ userRotation: cycleRotation(state.userRotation, 1) })),

  rotateCounterClockwise: () =>
    set((state) => ({ userRotation: cycleRotation(state.userRotation, -1) })),

  setOverlayEnabled: (enabled) => set({ overlayEnabled: enabled }),

  toggleOverlay: () => set((state) => ({ overlayEnabled: !state.overlayEnabled })),

  toggleNativeOverlay: () =>
    set((state) => ({ nativeOverlayEnabled: !state.nativeOverlayEnabled })),

  toggleOcrLineOverlay: () =>
    set((state) => ({
      ocrLineOverlayEnabled: !state.ocrLineOverlayEnabled,
      // Do not enable all overlays simultaneously by default.
      ocrWordOverlayEnabled: false,
      nativeOverlayEnabled: false,
    })),

  toggleOcrWordOverlay: () =>
    set((state) => ({
      ocrWordOverlayEnabled: !state.ocrWordOverlayEnabled,
      ocrLineOverlayEnabled: false,
      nativeOverlayEnabled: false,
    })),

  reset: () => set({ ...DEFAULTS, selectedDocumentId: get().selectedDocumentId }),
}));
