# Phase 5 security review (Task 2 foundation)

Engineering controls for the handwriting classifier foundation. This document
does **not** claim regulatory compliance.

## Local inference

- ONNX Runtime CPU only (`CPUExecutionProvider` requested explicitly)
- No Phase 5 network calls; no OpenAI client
- No automatic model download at startup

## Privacy

- Classifier APIs and health messages must not include document text, crop
  bytes, absolute model paths, or stack traces
- Class scores remain internal to the runtime service; public evidence fields
  are constrained enums and versions only

## Supply chain

- Model SHA-256 recorded in `model-record.json` and verified before readiness
- Strict manifest schema (`extra=forbid`)
- Dependency boundary allowlists `onnxruntime` / `onnx` to approved paths
- `test_fixture` packages cannot satisfy required production readiness

## Resource bounds

- Max crop pixel budget in preprocessing
- Bounded classifier batch size setting
- Lazy reusable session (no session-per-crop)

## Explicit exclusions

No OpenCV app imports, no local HTR engines, no vision-LLM code in Task 2.
