# Phase 5 security review (Tasks 2–3C)

Engineering controls for the handwriting classifier foundation and private crop
dataset tooling. This document does **not** claim regulatory compliance.

## Local inference (Task 2)

- ONNX Runtime CPU only (`CPUExecutionProvider` requested explicitly)
- No Phase 5 network calls; no OpenAI client
- No automatic model download at startup

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

## Supply chain

- Model SHA-256 recorded in `model-record.json` and verified before readiness
- Strict manifest schema (`extra=forbid`)
- Dependency boundary allowlists `onnxruntime` / `onnx` / OCR populate script
- Tasks 3A–3C add **no** new production dependencies (Pillow/NumPy/stdlib; OCR
  group only for offline populate)
- `test_fixture` packages cannot satisfy required production readiness

## Resource bounds

- Max crop pixel budget in preprocessing
- Bounded classifier batch size setting
- Lazy reusable session (no session-per-crop)
- Coverage overlays thin dense pages (deterministic box cap)

## Explicit exclusions

No OpenCV app imports, no local HTR engines, no vision-LLM code in Tasks 2–3C.
No training stack (torch/sklearn) and no Label Studio / Streamlit.
No fabricated human labels; no private split freeze; no held-out freeze while
source-group coverage is insufficient (ADR 0052).
