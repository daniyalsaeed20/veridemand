# handwriting_classifier (Phase 5 Task B4)

Expected package directory for a route-first ONNX router. Publish
`production_candidate` only when Task B4 safety + retention gates pass.

```text
models/handwriting_classifier/
├── README.md
├── model.onnx
├── labels.json
├── model-record.json
└── metrics.json
```

Schema: `phase5-handwriting-classifier-v3`  
Output: `route_logits` `[batch, 2]` = `vision_required`, `handwriting_present`

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
