# Phase 5 handwriting classifier model setup

## Defaults

- `HANDWRITING_ROUTER_ENABLED=false` — Phase 4 OCR unchanged
- `HANDWRITING_CLASSIFIER_REQUIRED=false`
- `HANDWRITING_CLASSIFIER_PATH=./models/handwriting_classifier` (package **directory**)
- Dual-risk thresholds (provisional until a calibrated package embeds values):
  - `HANDWRITING_ACCEPT_THRESHOLD=0.70`
  - `HANDWRITING_SAFE_LOW_THRESHOLD=0.20`
  - `NON_TEXT_ACCEPT_THRESHOLD=0.70`
  - `NON_TEXT_SAFE_LOW_THRESHOLD=0.20`
- Ordering: each `safe_low` must be strictly less than its `accept`
- Phase 5 does **not** call OpenAI

## Package layout (Task B3 dual-risk)

```text
models/handwriting_classifier/
  model.onnx
  labels.json          # structured: outputs + public_outcomes
  model-record.json    # schema phase5-handwriting-classifier-v2
  metrics.json
  README.md
```

`labels.json` example:

```json
{
  "output_semantics": "independent_binary_risk_logits",
  "outputs": ["handwriting_risk", "non_text_risk"],
  "public_outcomes": ["printed", "handwritten", "uncertain", "non_text"]
}
```

ONNX: input `image` `[batch,3,224,224]`; output `risk_logits` `[batch,2]`.

No automatic download on backend startup.

## Commands

```text
pnpm models:handwriting:verify
uv run python scripts/verify_handwriting_classifier.py
uv run python scripts/verify_handwriting_classifier.py --path <dir> --allow-test-fixture
pnpm models:handwriting:fixture   # regenerates dual-risk unit-test fixture only
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

## Publication rule

Publish `production_candidate` only when all Task B3 project safety gates pass.
Router remains disabled after packaging. Do not enable live OCR routing from
this setup doc alone.
