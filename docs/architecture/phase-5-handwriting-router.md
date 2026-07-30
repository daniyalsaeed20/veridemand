# Phase 5 handwriting router (architecture)

**Status:** Phase 5 in progress — Task 2 foundation complete, routing not
integrated into live OCR.

## Scope

Local ONNX image classifier for writing-style routing:

- Model classes: `printed`, `handwritten`, `non_text`
- Public outcomes: those three plus derived `uncertain`
- Coordinates remain detector-owned (`[0,1]`, top-left)
- No local HTR, OpenAI, OpenCV, or geometry invention

## Task 2 components

| Piece | Path |
|-------|------|
| Contracts | `backend/app/contracts/ocr.py` lifecycle/outcome/reason/evidence |
| Settings | `handwriting_router_enabled` (default false), thresholds, path |
| Service | `backend/app/extraction/handwriting_router/` |
| Verifier | `verify_classifier_package` + `scripts/verify_handwriting_classifier.py` |
| Health | `HealthService._check_handwriting_classifier` |

Phase 4 stamp sites still set `handwriting_assessment=pending_phase_5`. New
evidence fields are optional until Task 4.

## Explicit non-wiring

Task 2 does **not** call the classifier from:

- `visual/worker.py` / `process_page`
- `routing/repair_methods.py`
- `PaddleOcrAdapter.recognise*`

Overall progress remains capped at **65%**. Exclusive page terminals unchanged.

## Task 4 insertion (reference only)

Detect/geometry first → deterministic crops → classify → Paddle recognition
only for `printed`. See `docs/phases/phase-5-preflight-audit.md`.
