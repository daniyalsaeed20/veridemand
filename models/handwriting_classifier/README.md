# handwriting_classifier (Phase 5)

Expected package directory (no production model is committed in Task 2):

```text
models/handwriting_classifier/
├── README.md
├── model.onnx
├── labels.json
├── model-record.json
└── metrics.json
```

Configure `HANDWRITING_CLASSIFIER_PATH` to this directory (or to `model.onnx`).

Verify with:

```text
pnpm models:handwriting:verify
```

or:

```text
uv run python scripts/verify_handwriting_classifier.py
```

The router is **disabled by default** (`HANDWRITING_ROUTER_ENABLED=false`).
Do not place `test_fixture` packages here for production readiness.
