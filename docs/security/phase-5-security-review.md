# Phase 5 security review (Tasks 2–3B)

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
- Private Phase 5 crops/manifests/reviews live only under
  `fixtures/private/phase5/` (gitignored except `README.example.md`)
- Dataset manifests omit OCR text / transcripts / case names
- Offline populate writes geometry-only page-result JSON (text fields stripped)
- Loopback labeler binds `127.0.0.1` only; rejects path traversal; no
  `localStorage` of private data; not mounted in production FastAPI
- Committed readiness reports use opaque aggregate counts only; small strata
  merged into `other`
- Primary-review queue is gitignored; queue UI does not expose candidate source

## Supply chain

- Model SHA-256 recorded in `model-record.json` and verified before readiness
- Strict manifest schema (`extra=forbid`)
- Dependency boundary allowlists `onnxruntime` / `onnx` / OCR populate script
- Tasks 3A–3B add **no** new production dependencies (Pillow/NumPy/stdlib; OCR
  group only for offline populate)
- `test_fixture` packages cannot satisfy required production readiness

## Resource bounds

- Max crop pixel budget in preprocessing
- Bounded classifier batch size setting
- Lazy reusable session (no session-per-crop)

## Explicit exclusions

No OpenCV app imports, no local HTR engines, no vision-LLM code in Tasks 2–3B.
No training stack (torch/sklearn) and no Label Studio / Streamlit.
No fabricated human labels; no private split freeze in Task 3B.
