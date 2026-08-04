# Phase 5 security review (Tasks 2–B3)

Engineering controls for the handwriting classifier foundation, private crop
dataset tooling, Task B/B2 three-class baselines, and Task B3 dual-risk
safety-first router. This document does **not** claim regulatory compliance.

## Local inference

- ONNX Runtime CPU only (`CPUExecutionProvider` requested explicitly)
- No Phase 5 network calls; no OpenAI client
- No automatic model download at startup
- Dual-risk packages use `independent_binary_risk_logits`; historical v1
  three-class fixtures remain test-only

## Model development (B / B2 / B3)

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
- Derived ONNX package may be committed only if Task B3 safety + slice gates
  pass; router remains disabled; no OCR integration in B3
- No new private labels and no additional public corpus in Task B3

## Privacy

- Classifier APIs and health messages must not include document text, crop
  bytes, absolute model paths, or stack traces
- Risk scores remain internal; public evidence fields are constrained enums
  and versions only
- Private Phase 5 crops/manifests/reviews/overlays/pilot queues live only under
  `fixtures/private/phase5/` (gitignored except `README.example.md`)
- Dataset manifests omit OCR text / transcripts / case names

## Dependency boundary

- Production: `onnxruntime` 1.28.0
- model-dev: `torch` 2.6.0, `torchvision` 0.21.0, `onnx` 1.22.0
- No OpenCV app imports; no local HTR; no OpenAI

## Residual risks

- Six source groups limit release claims (prototype OOF only)
- Domain shift between ASAP short answers and project signatures/cursive
- Disabled router does not yet enforce the Paddle-bypass invariant in live OCR
