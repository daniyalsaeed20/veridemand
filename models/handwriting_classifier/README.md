# handwriting_classifier (Phase 5 Task B2)

Expected package directory. Task B2 did **not** publish a `production_candidate`
(safety + slice gates still failing after ASAP supplementation).

```text
models/handwriting_classifier/
├── README.md
├── model.onnx
├── labels.json
├── model-record.json
└── metrics.json
```

Public training data (when prepared locally): Handwritten ASAP Short Answer
Scoring (Zenodo 8088866, CC BY 4.0). Raw archives are gitignored under
`model_development/.data/handwritten_asap/`.

Configure `HANDWRITING_CLASSIFIER_PATH` to this directory (or to `model.onnx`).

Verify with:

```text
pnpm models:handwriting:verify
```

The router is **disabled by default** (`HANDWRITING_ROUTER_ENABLED=false`).
Do not place `test_fixture` packages here for production readiness.
Do not integrate into live OCR until a later task clears the gates.
