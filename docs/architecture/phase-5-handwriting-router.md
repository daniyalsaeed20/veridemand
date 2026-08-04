# Phase 5 handwriting router (architecture)

**Status:** Phase 5 in progress — Task B project-only classifier requires
additional training data before runtime integration. Router remains disabled;
not wired into live OCR.

## Scope

Local ONNX image classifier for writing-style routing:

- Model classes: `printed`, `handwritten`, `non_text`
- Public outcomes: those three plus derived `uncertain`
- Coordinates remain detector-owned (`[0,1]`, top-left)
- No local HTR, OpenAI, OpenCV, or geometry invention

### Routing doctrine

```text
printed     → Paddle printed-text recognition
handwritten → no Paddle; preserve detector ID/geometry; reserved_for_vision / pending_phase_6
uncertain   → no Paddle; preserve detector ID/geometry; reserved_for_vision / pending_phase_6
non_text    → no Paddle; suppress from text recognition
```

“Route to vision” means **reservation only** — not a vision-provider request in
Phase 5. Critical invariant (later Tasks C–D): no handwritten or uncertain
region may ever be passed to Paddle recognition.

## Task B training tooling

| Piece | Path |
|-------|------|
| Model-dev package | `model_development/handwriting_classifier/` |
| Train/export CLI | `scripts/phase5/train_handwriting_classifier.py` |
| Runtime package dir | `models/handwriting_classifier/` (no production_candidate yet) |
| Evaluation | `docs/evaluation/phase-5-classifier-*.md` |

Training uses Torch/Torchvision only under `model-dev`. Production backend must
not import them (dependency-boundary check).

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
