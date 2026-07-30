# ADR 0050 — ONNX Runtime CPU dependency and import boundary

## Status

Accepted (Phase 5 Task 2)

## Context

Phase 5 inference needs ONNX Runtime on CPU. OpenAI, OpenCV, and HTR engines
must remain forbidden. Structural tooling (`onnx`) should stay out of ordinary
application services where possible.

## Decision

- Add CPU `onnxruntime` as a direct project dependency (not `onnxruntime-gpu`).
- Add `onnx` under the `model-dev` dependency group for checker/fixture tooling.
- Allow `onnxruntime` imports only under
  `backend/app/extraction/handwriting_router/` and approved verify scripts.
- Allow `onnx` imports only under handwriting router verification paths,
  generate/verify scripts, and tests.
- Health integrates via `HandwritingClassifierService` and does not import
  `onnxruntime` directly.
- `scripts/check_dependency_boundary.py` enforces these allowlists.

## Consequences

Phase 4 Paddle boundaries are unchanged. Training libraries (torch/sklearn)
remain out of Task 2.
