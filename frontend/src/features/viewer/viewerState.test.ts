import { beforeEach, describe, expect, it } from "vitest";

import { VIEWER_MAX_SCALE, VIEWER_MIN_SCALE } from "./constants";
import { useViewerStore } from "./viewerState";

const INITIAL_STATE = useViewerStore.getState();

beforeEach(() => {
  useViewerStore.setState(INITIAL_STATE, true);
});

describe("useViewerStore defaults", () => {
  it("starts with no document selected and sensible defaults", () => {
    const state = useViewerStore.getState();
    expect(state.selectedDocumentId).toBeNull();
    expect(state.pageNumber).toBe(1);
    expect(state.zoomMode).toBe("fit_width");
    expect(state.userRotation).toBe(0);
    expect(state.overlayEnabled).toBe(false);
    expect(state.nativeOverlayEnabled).toBe(false);
  });
});

describe("selectDocument (document reset)", () => {
  it("resets page/zoom/rotation/overlay to defaults on every new selection", () => {
    useViewerStore.setState({
      pageNumber: 4,
      zoomMode: "manual",
      manualScale: 2.5,
      userRotation: 180,
      overlayEnabled: true,
    });

    useViewerStore.getState().selectDocument("doc_" + "1".repeat(32));

    const state = useViewerStore.getState();
    expect(state.selectedDocumentId).toBe("doc_" + "1".repeat(32));
    expect(state.pageNumber).toBe(1);
    expect(state.zoomMode).toBe("fit_width");
    expect(state.userRotation).toBe(0);
    expect(state.overlayEnabled).toBe(false);
  });

  it("selecting a different document resets state again, even mid-session", () => {
    useViewerStore.getState().selectDocument("doc_" + "1".repeat(32));
    useViewerStore.getState().setPageNumber(3);
    useViewerStore.getState().rotateClockwise();

    useViewerStore.getState().selectDocument("doc_" + "2".repeat(32));

    const state = useViewerStore.getState();
    expect(state.selectedDocumentId).toBe("doc_" + "2".repeat(32));
    expect(state.pageNumber).toBe(1);
    expect(state.userRotation).toBe(0);
  });

  it("clears the selection when passed null", () => {
    useViewerStore.getState().selectDocument("doc_" + "1".repeat(32));
    useViewerStore.getState().selectDocument(null);
    expect(useViewerStore.getState().selectedDocumentId).toBeNull();
  });
});

describe("page navigation", () => {
  it("never allows a page number below 1", () => {
    useViewerStore.getState().setPageNumber(0);
    expect(useViewerStore.getState().pageNumber).toBe(1);
    useViewerStore.getState().setPageNumber(-3);
    expect(useViewerStore.getState().pageNumber).toBe(1);
  });
});

describe("zoom", () => {
  it("setManualScale switches to manual mode and clamps the scale", () => {
    useViewerStore.getState().setManualScale(10);
    expect(useViewerStore.getState().zoomMode).toBe("manual");
    expect(useViewerStore.getState().manualScale).toBe(VIEWER_MAX_SCALE);

    useViewerStore.getState().setManualScale(0.001);
    expect(useViewerStore.getState().manualScale).toBe(VIEWER_MIN_SCALE);
  });

  it("zoomIn/zoomOut switch to manual mode and step the scale", () => {
    useViewerStore.getState().zoomIn(1);
    expect(useViewerStore.getState().zoomMode).toBe("manual");
    expect(useViewerStore.getState().manualScale).toBeCloseTo(1.25);

    useViewerStore.getState().zoomOut(1.25);
    expect(useViewerStore.getState().manualScale).toBeCloseTo(1);
  });

  it("zoomIn clamps at VIEWER_MAX_SCALE", () => {
    useViewerStore.getState().zoomIn(VIEWER_MAX_SCALE);
    expect(useViewerStore.getState().manualScale).toBe(VIEWER_MAX_SCALE);
  });

  it("zoomOut clamps at VIEWER_MIN_SCALE", () => {
    useViewerStore.getState().zoomOut(VIEWER_MIN_SCALE);
    expect(useViewerStore.getState().manualScale).toBe(VIEWER_MIN_SCALE);
  });

  it("setZoomMode does not change the manual scale", () => {
    useViewerStore.getState().setManualScale(1.5);
    useViewerStore.getState().setZoomMode("fit_page");
    expect(useViewerStore.getState().zoomMode).toBe("fit_page");
    expect(useViewerStore.getState().manualScale).toBeCloseTo(1.5);
  });
});

describe("rotation", () => {
  it("rotates clockwise and counter-clockwise in 90 degree steps", () => {
    useViewerStore.getState().rotateClockwise();
    expect(useViewerStore.getState().userRotation).toBe(90);
    useViewerStore.getState().rotateClockwise();
    expect(useViewerStore.getState().userRotation).toBe(180);
    useViewerStore.getState().rotateCounterClockwise();
    expect(useViewerStore.getState().userRotation).toBe(90);
  });
});

describe("overlay toggle", () => {
  it("toggleOverlay flips the overlay flag", () => {
    expect(useViewerStore.getState().overlayEnabled).toBe(false);
    useViewerStore.getState().toggleOverlay();
    expect(useViewerStore.getState().overlayEnabled).toBe(true);
    useViewerStore.getState().toggleOverlay();
    expect(useViewerStore.getState().overlayEnabled).toBe(false);
  });

  it("setOverlayEnabled sets an explicit value", () => {
    useViewerStore.getState().setOverlayEnabled(true);
    expect(useViewerStore.getState().overlayEnabled).toBe(true);
    useViewerStore.getState().setOverlayEnabled(false);
    expect(useViewerStore.getState().overlayEnabled).toBe(false);
  });
});

describe("native overlay toggle", () => {
  it("toggleNativeOverlay flips the native-word-box flag", () => {
    expect(useViewerStore.getState().nativeOverlayEnabled).toBe(false);
    useViewerStore.getState().toggleNativeOverlay();
    expect(useViewerStore.getState().nativeOverlayEnabled).toBe(true);
    useViewerStore.getState().toggleNativeOverlay();
    expect(useViewerStore.getState().nativeOverlayEnabled).toBe(false);
  });
});

describe("reset", () => {
  it("restores defaults while keeping the current selection", () => {
    useViewerStore.getState().selectDocument("doc_" + "3".repeat(32));
    useViewerStore.getState().setPageNumber(5);
    useViewerStore.getState().rotateClockwise();
    useViewerStore.getState().setOverlayEnabled(true);

    useViewerStore.getState().reset();

    const state = useViewerStore.getState();
    expect(state.selectedDocumentId).toBe("doc_" + "3".repeat(32));
    expect(state.pageNumber).toBe(1);
    expect(state.userRotation).toBe(0);
    expect(state.overlayEnabled).toBe(false);
  });
});
