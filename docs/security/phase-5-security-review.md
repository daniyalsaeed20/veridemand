# Phase 5 security review (Tasks 2–B4)

Engineering controls for the handwriting classifier foundation, private crop
dataset tooling, Task B/B2/B3 failed baselines, and Task B4 route-first
vision-reservation router. This document does **not** claim regulatory
compliance.

## Local inference

- ONNX Runtime CPU only (`CPUExecutionProvider` requested explicitly)
- No Phase 5 network calls; no OpenAI client
- No automatic model download at startup
- Route-first packages use `route_first_independent_logits` (schema v3);
  historical v1 three-class and v2 dual-risk fixtures remain test/baseline only

## Model development (B / B2 / B3 / B4)

- Torch / Torchvision / onnxscript remain in the `model-dev` group only
- Forbidden from `backend/app` imports via dependency-boundary check
- Private training manifests, checkpoints, and OOF prediction dumps stay under
  gitignored `fixtures/private/phase5/model-dev/` and
  `model_development/.artifacts/`
- Public ASAP archives, extracts, and prepared crops stay under gitignored
  `model_development/.data/handwritten_asap/`
- Committed evaluation reports use aggregates only (no crop/page/reviewer IDs,
  paths, text, or montages)
- Handwritten ASAP (Zenodo 8088866, CC BY 4.0) via explicit prepare only;
  MD5 + local SHA-256 verified; NIST SD19 / EMNIST forbidden
- Derived ONNX package may be committed only if Task B4 safety + retention
  gates pass; router remains disabled; no OCR integration in B4
- No new private labels and no additional public corpus in Task B4

## Privacy

- Classifier APIs and health messages must not include document text, crop
  bytes, absolute model paths, or stack traces
- Route scores remain internal; public evidence fields are constrained enums
  and versions only
- Private Phase 5 crops/manifests/reviews/overlays/pilot queues live only under
  `fixtures/private/phase5/` (gitignored except `README.example.md`)
- Dataset manifests omit OCR text / transcripts / case names

## Non-regression

- Live OCR / Paddle / page routes / progress (65% cap) / fair scheduling
  unchanged
- `HANDWRITING_ROUTER_ENABLED=false` by default
- No Phase 6 vision provider calls
