// Viewer constants (Phase 2).
//
// These values mirror the backend defaults in `backend/app/settings/config.py`
// (`viewer_min_scale`, `viewer_max_scale`, `viewer_scale_step`,
// `canonical_page_dimension_tolerance_points`). Keep them in sync manually
// until the settings are exposed to the frontend via a contract.

export const VIEWER_MIN_SCALE = 0.25;
export const VIEWER_MAX_SCALE = 4.0;
export const VIEWER_SCALE_STEP = 0.25;

// Matches `canonical_page_dimension_tolerance_points` on the backend: the
// maximum allowed difference (in PDF points) between what PDF.js reports for a
// page at scale 1 and what the backend canonical metadata reports before the
// viewer treats the page as suspect and disables its overlay.
export const DIMENSION_TOLERANCE_POINTS = 0.5;

export const ZOOM_MODES = ["manual", "fit_width", "fit_page"] as const;
export type ZoomMode = (typeof ZOOM_MODES)[number];

export const ROTATION_DEGREES = [0, 90, 180, 270] as const;
export type RotationDegrees = (typeof ROTATION_DEGREES)[number];
