# Phase 5 handwriting classifier model setup

## Defaults

- `HANDWRITING_ROUTER_ENABLED=false` — Phase 4 OCR unchanged
- `HANDWRITING_CLASSIFIER_REQUIRED=false`
- `HANDWRITING_CLASSIFIER_PATH=./models/handwriting_classifier` (package **directory**)
- Thresholds are **provisional** (not calibrated): printed 0.85, handwriting
  0.70, non_text 0.80, minimum margin 0.10
- Phase 5 does **not** call OpenAI

## Package layout

```text
models/handwriting_classifier/
  model.onnx
  labels.json          # exactly printed, handwritten, non_text
  model-record.json
  metrics.json
```

No automatic download on backend startup.

## Commands

```text
pnpm models:handwriting:verify
uv run python scripts/verify_handwriting_classifier.py
uv run python scripts/verify_handwriting_classifier.py --path <dir> --allow-test-fixture
pnpm models:handwriting:fixture   # regenerates unit-test fixture only
pnpm models:handwriting:manifest  # build private training manifest (model-dev)
pnpm phase5:model-data:asap:prepare  # download/verify Handwritten ASAP (model-dev)
pnpm models:handwriting:train     # LOSGO + threshold search + export (model-dev)
```

Handwritten ASAP (Zenodo 8088866, CC BY 4.0) is downloaded only by the explicit
prepare command into gitignored `model_development/.data/handwritten_asap/`.
It is never fetched at backend startup or during normal application tests.
NIST SD19 / EMNIST are not used.

### Model-development dependencies

Install the training stack separately:

```text
uv sync --group model-dev
```

Includes `torch==2.6.0`, `torchvision==0.21.0`, `onnx`, and `onnxscript`.
These are **not** production backend dependencies. Pretrained ImageNet weights
download into the local Torch cache (outside Git) only when training tooling
runs — never on application startup.

**Windows note:** do not sync `model-dev` and `ocr` into the same active
environment at once. PaddleOCR pulls `modelscope`, which imports `torch` and can
conflict with the Task B Torch CPU wheel (`shm.dll` load errors). Use
`uv sync --group model-dev` for training/tests, then
`uv sync --group ocr --group dev` before Phase 4 OCR regression.

Keep `HANDWRITING_ROUTER_ENABLED=false` until a later integration task.
Task B2 may write a `production_candidate` package only when project OOF safety
and cursive/signature slice gates pass; the router stays disabled.
## Readiness

| Mode | `/health/live` | `/health/ready` |
|------|----------------|-----------------|
| Router disabled | ok | ready (`not_configured`) |
| Enabled optional + ready | ok | ready |
| Enabled optional + broken | ok | ready (check fails, not required) |
| Enabled required + ready | ok | ready |
| Enabled required + broken | ok | **not_ready** |

`test_fixture` packages never satisfy production-required readiness.

## Common failures

Missing files, checksum mismatch, invalid labels/manifest, CPU provider
unavailable, smoke inference failure. Messages never include absolute paths.
