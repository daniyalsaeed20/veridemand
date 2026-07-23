# Phase 4.4 — Visual pipeline and canonical viewer regression

## Starting branch and commit

- Starting branch: `fix/phase-4-adaptive-image-ocr-performance`
- Starting HEAD: `4d63df465bce4e085236b7b84ee5b0410e4f06ab` (`phase-4-visual-detection-printed-ocr-v1.4`)
- Corrective branch: `fix/phase-4-visual-pipeline-viewer-regression`
- Comparison worktree: `../VeriDemand-phase4-v1.3` at `phase-4-visual-detection-printed-ocr-v1.3` (`3eeca6c`)
- Throughput WIP stashed as `wip-phase44-throughput` (not landed on this branch)

## Regression range

| Layer | Finding |
|-------|---------|
| Clean v1.4 (`4d63df4`) | Uses legacy `_run_visual`; no fair-scheduler kwargs. Universal immediate abort not present on clean HEAD. |
| Uncommitted throughput WIP | Introduced `_register_visual_fair` publishing `document_pages_total` / `visual_pages_*` to `EventBroker.publish` **before** the broker accepted those parameters. |
| First bad state | Working-tree fair path after page selection / visibility probe — `TypeError: unexpected keyword argument 'document_pages_total'`. |

Exact visual exception (WIP / class of bug fixed here):

- Exception: `TypeError`
- File: `backend/app/progress/broker.py` (`EventBroker.publish`)
- Trigger: `backend/app/processing/coordinator.py` post-`prepare_document` `_safe_publish(... document_pages_total=...)`
- Last successful operation: `native_visibility_reconciliation` / `visual_page_selection`
- Why every document failed: every Phase 4 document hits the same post-selection publish before OCR inference

## Corrections delivered

1. Structured `logger.exception` extras on visual failure (`failing_operation`, `exception_type`, …).
2. `_safe_publish` never aborts extraction on telemetry errors.
3. `EventBroker` + `ProgressEvent` accept optional selection/ETA fields so the TypeError class cannot recur.
4. `VisualOcrService.publish_terminal_failure_summary` always writes a terminal summary (no document text); failure paths prefer `visual_processing_partial` when native results exist; never clear `canonical_view_available`.
5. Canonical PDF request privacy-safe logging; range 0-1023 + SHA-256 stability test.
6. Viewer: optional native/visual panels; PDF load generation + Retry; blank-canvas detection; open-in-new-tab.

## Phase boundary

- Fair scheduler / queue reordering / ETA UX **not** enabled on this branch.
- Phase 5 not started.
- No tag moved; completion tag deferred until CI + private subset green.

## Tests

- `backend/tests/test_phase44_visual_pipeline_regression.py`
- Extended `backend/tests/test_canonical_api.py`
- `frontend/src/features/viewer/phase44ViewerRegression.test.ts`
