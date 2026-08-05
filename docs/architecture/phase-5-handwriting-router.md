# Phase 5 handwriting router (architecture)

**Status:** Phase 5 in progress — Task B4 route-first model under evaluation.
Router remains disabled; not wired into live OCR.

## Scope

Local ONNX image classifier for writing-style routing:

- Model outputs: independent `vision_required` and `handwriting_present` logits
- Public outcomes: `printed`, `handwritten`, `uncertain`, `non_text`
  (`non_text` from Phase 4 suppression; model policy never emits it)
- Coordinates remain detector-owned (`[0,1]`, top-left)
- No local HTR, OpenAI, OpenCV, or geometry invention

Task B / B2 three-class softmax and Task B3 dual-risk remain
**failed baselines — superseded for safety evaluation**.

### Routing doctrine

```text
printed     → Paddle printed-text recognition
handwritten → no Paddle; preserve detector ID/geometry; reserved_for_vision / pending_phase_6
uncertain   → no Paddle; preserve detector ID/geometry; reserved_for_vision / pending_phase_6
non_text    → no Paddle; suppress from text recognition (Phase 4)
```

Critical invariant (later Tasks C–D): no handwritten or uncertain region may
ever be passed to Paddle recognition.

## Task B4 training tooling

| Piece | Path |
|-------|------|
| Model-dev package | `model_development/handwriting_classifier/` |
| Train/export CLI | `scripts/phase5/train_handwriting_classifier.py` |
| Runtime package dir | `models/handwriting_classifier/` |
| Evaluation | `docs/evaluation/phase-5-classifier-*.md` |
| ADRs | 0068–0071 (route-first); 0063–0067 (dual-risk baseline); 0059–0062 (ASAP) |

Training uses Torch/Torchvision only under `model-dev`. Production backend must
not import them (dependency-boundary check).

## Task 2 components

| Piece | Path |
|-------|------|
| Contracts | `backend/app/contracts/ocr.py` lifecycle/outcome/reason/evidence |
| Settings | `handwriting_router_enabled` (default false), route-first thresholds, path |
| Service | `backend/app/extraction/handwriting_router/` |
| Verifier | `verify_classifier_package` + `scripts/verify_handwriting_classifier.py` |
| Health | `HealthService._check_handwriting_classifier` |

Phase 4 stamp sites still set `handwriting_assessment=pending_phase_5`. New
evidence fields are optional until integration.

## Explicit non-wiring

Does **not** call the classifier from:

- `backend/app/extraction/visual/paddle_adapter.py`
- `backend/app/extraction/visual/worker.py`
- `backend/app/extraction/routing/`
- `backend/app/extraction/repair/`
- Progress remains capped at **65%**; fair scheduling unchanged.
