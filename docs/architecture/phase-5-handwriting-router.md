# Phase 5 handwriting router (architecture)

**Status:** Phase 5 in progress — safety-first model remains below project
routing gates. Router remains disabled; not wired into live OCR.

## Scope

Local ONNX image classifier for writing-style routing:

- Model outputs: independent `handwriting_risk` and `non_text_risk` logits
- Public outcomes: `printed`, `handwritten`, `uncertain`, `non_text`
  (derived by safety-first abstention; printed is guarded, not a model class)
- Coordinates remain detector-owned (`[0,1]`, top-left)
- No local HTR, OpenAI, OpenCV, or geometry invention

Task B / B2 three-class softmax remains a
**prototype baseline — superseded for safety evaluation**.

### Routing doctrine

```text
printed     → Paddle printed-text recognition
handwritten → no Paddle; preserve detector ID/geometry; reserved_for_vision / pending_phase_6
uncertain   → no Paddle; preserve detector ID/geometry; reserved_for_vision / pending_phase_6
non_text    → no Paddle; suppress from text recognition
```

Critical invariant (later Tasks C–D): no handwritten or uncertain region may
ever be passed to Paddle recognition.

## Task B3 training tooling

| Piece | Path |
|-------|------|
| Model-dev package | `model_development/handwriting_classifier/` |
| Train/export CLI | `scripts/phase5/train_handwriting_classifier.py` |
| Runtime package dir | `models/handwriting_classifier/` |
| Evaluation | `docs/evaluation/phase-5-classifier-*.md` |
| ADRs | 0063–0067 (dual-risk); 0059–0062 (ASAP / slices) |

Training uses Torch/Torchvision only under `model-dev`. Production backend must
not import them (dependency-boundary check).

## Task 2 components

| Piece | Path |
|-------|------|
| Contracts | `backend/app/contracts/ocr.py` lifecycle/outcome/reason/evidence |
| Settings | `handwriting_router_enabled` (default false), dual-risk thresholds, path |
| Service | `backend/app/extraction/handwriting_router/` |
| Verifier | `verify_classifier_package` + `scripts/verify_handwriting_classifier.py` |
| Health | `HealthService._check_handwriting_classifier` |

Phase 4 stamp sites still set `handwriting_assessment=pending_phase_5`. New
evidence fields are optional until integration.

## Explicit non-wiring

Does **not** call the classifier from:

- `visual/worker.py` / `process_page`
- `routing/repair_methods.py`
- `PaddleOcrAdapter.recognise*`

Overall progress remains capped at **65%**. Exclusive page terminals unchanged.

## Task 4 insertion (reference only)

Detect/geometry first → deterministic crops → classify → Paddle recognition
only for `printed`. See `docs/phases/phase-5-preflight-audit.md`.
