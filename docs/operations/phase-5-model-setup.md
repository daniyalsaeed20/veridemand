# Phase 5 handwriting classifier model setup

## Defaults

- `HANDWRITING_ROUTER_ENABLED=false` — Phase 4 OCR unchanged
- `HANDWRITING_CLASSIFIER_REQUIRED=false`
- `HANDWRITING_CLASSIFIER_PATH=./models/handwriting_classifier` (package **directory**)
- `PHASE5_DETECT_FIRST_SHADOW_ENABLED=false` — detector-first modules off in normal profiles
- Route-first thresholds (provisional until a calibrated package embeds values):
  - `LOCAL_OCR_SAFE_THRESHOLD=0.20`
  - `VISION_REQUIRED_THRESHOLD=0.70`
  - `HANDWRITING_ACCEPT_THRESHOLD=0.70`
- Ordering: `local_ocr_safe` must be strictly less than `vision_required`
- Phase 5 does **not** call OpenAI

## Detector-first shadow (Task C0)

Separate PaddleX det/rec modules reuse the configured local OCR assets
(`PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec` by default under
`OCR_MODEL_ROOT`). They are **not** loaded by the visual worker.

```text
pnpm models:ocr:verify
pnpm phase5:detector-corpus:build
pnpm phase5:detector-corpus:compare
pnpm phase5:detector-corpus:coverage
```

Do not sync `model-dev` for these commands — use the OCR group only.

Private corpus version: `phase5-detector-first-regions-v1` under
`fixtures/private/phase5/detector-first/` (gitignored).

## Detector recall calibration (Task C1)

Shadow-only. Does **not** replace the live mobile detector.

```text
pnpm models:ocr:bootstrap:server-det
pnpm phase5:detector-calib:baseline
pnpm phase5:detector-calib:grid
pnpm phase5:detector-calib:select
```

- Server assets: `.models/paddleocr/PP-OCRv5_server_det/` (gitignored)
- Live `OCR_DETECTION_MODEL_NAME` remains `PP-OCRv5_mobile_det`
- Dual merge algorithm: `phase5-dual-detector-merge-v1` (offline only)
- Architecture: `docs/architecture/phase-5-detector-calibration.md`
- Evidence: `docs/evaluation/phase-5-detector-candidate-comparison.md`

Known-seed gate result: **DETECTOR COVERAGE STILL INSUFFICIENT** — do not
retrain the classifier until a candidate passes.

## Package layout (Task B4 route-first)

```text
models/handwriting_classifier/
  model.onnx
  labels.json          # structured: outputs + public_outcomes
  model-record.json    # schema phase5-handwriting-classifier-v3
  metrics.json
  README.md
```

`labels.json` example:

```json
{
  "output_semantics": "route_first_independent_logits",
  "outputs": ["vision_required", "handwriting_present"],
  "public_outcomes": ["printed", "handwritten", "uncertain", "non_text"]
}
```

ONNX: input `image` `[batch,3,224,224]`; output `route_logits` `[batch,2]`.

No automatic download on backend startup.

## Commands

```text
pnpm models:handwriting:verify
uv run python scripts/verify_handwriting_classifier.py
uv run python scripts/verify_handwriting_classifier.py --path <dir> --allow-test-fixture
pnpm models:handwriting:fixture   # regenerates route-first unit-test fixture only
pnpm models:handwriting:manifest  # build private training manifest (model-dev)
pnpm phase5:model-data:asap:prepare  # download/verify Handwritten ASAP (model-dev)
pnpm models:handwriting:train     # LOSGO + threshold search + export (model-dev)
```

Handwritten ASAP (Zenodo 8088866, CC BY 4.0) is downloaded only by the explicit
prepare command into gitignored `model_development/.data/handwritten_asap/`.
It is never fetched at backend startup or during normal application tests.
NIST SD19 / EMNIST are not used.

## Windows environments

Do not sync `model-dev` (Torch) and `ocr` (Paddle) into the same environment —
known `shm.dll` conflicts on Windows.

### OCR acceptance environment (required for release gates)

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-ocr"
uv sync --group ocr
uv run --group ocr python -c "import importlib.util as u; assert u.find_spec('torch') is None; assert u.find_spec('torchvision') is None; import paddle; print('paddle_ok')"
uv run --group ocr python scripts/verify_ocr_runtime.py
```

Contains production/core dependencies plus the OCR group (PaddleOCR /
PaddlePaddle / PaddleX). Torch and Torchvision must be absent.

### Model-development environment (offline only)

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-model-dev"
uv sync --group model-dev
```

May contain Torch / Torchvision / ONNX model-development tools. Paddle import
success is **not** required on Windows. Task D does not retrain models; use this
environment only for model-development unit tests that are independent of OCR.

Detect-first module load stubs ModelScope when a mixed-env Torch import would
crash, because local model dirs do not need hub downloads. Prefer the dedicated
OCR-only venv for `pnpm models:ocr:verify`, corpus commands, feature-off /
feature-on acceptance, and Playwright E2E (`.venv-ocr` preferred when present).

## Publication rule

Publish `production_candidate` only when all Task B4 project safety gates pass.
**None published:** B4 decision remains `ROUTE-FIRST MODEL STILL NOT SAFE`.
Router remains disabled after packaging. Do not enable live OCR routing from
this setup doc alone. Retrain any future router on detector-first crops before
live integration (Task C0).
