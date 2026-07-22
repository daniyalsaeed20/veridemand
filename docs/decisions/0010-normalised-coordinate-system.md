# ADR 0010 - Normalised coordinate system

- Status: Accepted
- Date: 2026-07-22
- Phase: 2

## Context

Overlays, crops, and later extraction spans need a stable, format-agnostic way to
reference regions on a page across PDF, rendered images, and rotated views.

## Decision

- All **display coordinates** use normalised page space: origin **top-left**,
  x increases right, y increases down, values in `[0, 1]`.
- Contract types: `NormalisedPoint`, `NormalisedBoundingBox`, `NormalisedPolygon`,
  `Geometry` (polygon + containing bbox). Pydantic validators reject non-finite
  values, degenerate polygons, and bboxes that do not contain their polygon.
- **Intrinsic PDF rotation** is stored per page in canonical metadata
  (`intrinsic_rotation`: 0/90/180/270). The default visual coordinate system
  already accounts for it; additional viewer rotation is applied client-side via
  `rotate_normalised_point` (clockwise mappings).
- Phase 2 overlay proof uses a fixed `phase2_alignment_geometry()` rectangle —
  synthetic only, not extracted content.

## Consequences

- Frontend and backend share generated contract shapes; no hand-maintained duplicate
  field lists.
- Later phases can attach real spans as `Geometry` without changing the coordinate
  convention.
- Viewer rotation math must stay aligned with backend rotation helpers.
