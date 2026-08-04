# Phase 5 security review (Tasks 2–B2)

Engineering controls for the handwriting classifier foundation, private crop
dataset tooling, Task B model-development, and Task B2 ASAP supplementation.
This document does **not** claim regulatory compliance.

## Local inference (Task 2)

- ONNX Runtime CPU only (`CPUExecutionProvider` requested explicitly)
- No Phase 5 network calls; no OpenAI client
- No automatic model download at startup

## Task B / B2 model development

- Torch / Torchvision / onnxscript remain in the `model-dev` group only
- Forbidden from `backend/app` imports via dependency-boundary check
- Private training manifests, checkpoints, and OOF prediction dumps stay under
  gitignored `fixtures/private/phase5/model-dev/` and
  `model_development/.artifacts/`
- Public ASAP archives, extracts, and prepared crops stay under gitignored
  `model_development/.data/handwritten_asap/`
- Committed evaluation reports use aggregates only (no crop/page/reviewer IDs,
  paths, text, or montages)
- Task B: no public handwriting dataset download
- Task B2: Handwritten ASAP (Zenodo 8088866, CC BY 4.0) via explicit
  `pnpm phase5:model-data:asap:prepare` only; MD5 + local SHA-256 verified;
  NIST SD19 / EMNIST forbidden
- Derived ONNX package may be committed only if safety + slice gates pass;
  router remains disabled; no OCR integration in B2

## Privacy

- Classifier APIs and health messages must not include document text, crop
  bytes, absolute model paths, or stack traces
- Class scores remain internal to the runtime service; public evidence fields
  are constrained enums and versions only
- Private Phase 5 crops/manifests/reviews/overlays/pilot queues live only under
  `fixtures/private/phase5/` (gitignored except `README.example.md`)
- Dataset manifests omit OCR text / transcripts / case names
- Offline populate writes geometry-only page-result JSON (text fields stripped)
- Loopback labeler and coverage server bind `127.0.0.1` only; reject path
  traversal; no `localStorage` of private data; not mounted in production FastAPI
- Committed readiness / pilot / provenance reports use opaque aggregates only
- Candidate provenance and sampling reasons are never shown to crop reviewers
- Task 3C creates **no** fabricated private human labels or coverage events
- ASAP transcription / ASAP IDs are discarded; public subset manifests never
  reference private crop IDs

## Supply chain

- Model SHA-256 recorded in `model-record.json` and verified before readiness
- Strict manifest schema (`extra=forbid`)
- Dependency boundary allowlists `onnxruntime` / `onnx` / OCR populate script;
  forbids `torch` / `torchvision` in production application code
- Tasks 3A–3C add **no** new production dependencies (Pillow/NumPy/stdlib; OCR
  group only for offline populate)
- Task B adds torch/torchvision/onnxscript to **`model-dev` only**
- Task B2 adds no new Python packages; ASAP is model-dev training data under
  CC BY 4.0 with attribution in package provenance
- Zip extraction rejects path traversal
- `test_fixture` packages cannot satisfy required production readiness

## Resource bounds

- Max crop pixel budget in preprocessing
- Bounded classifier batch size setting
- Lazy reusable session (no session-per-crop)
- Coverage overlays thin dense pages (deterministic box cap)

## Explicit exclusions

No OpenCV app imports, no local HTR engines, no vision-LLM code in Tasks 2–B2.
No training stack (torch/sklearn) in production FastAPI and no Label Studio /
Streamlit. No fabricated human labels; no private split freeze; no held-out
freeze while source-group coverage is insufficient (ADR 0052).
No NIST SD19 / EMNIST.