# ADR 0058 — ONNX export and package status

## Status

Accepted (Phase 5 Task B)

**Superseded for production-candidate evaluation** by Task B3 dual-risk export
(`risk_logits` `[batch, 2]`, `independent_binary_risk_logits`, schema v2).
The package layout and verifier pattern remain; output contract and labels
schema change under ADR 0063–0064.

## Context

Production inference uses ONNX Runtime CPU only. Training uses PyTorch. The
existing package verifier requires `model.onnx`, `labels.json`,
`model-record.json`, and `metrics.json`, with strict I/O and checksum checks.
`production_candidate` / `released` statuses require train/val/held-out manifest
SHA-256 fields.

## Decision

1. Export the selected final model with:
   - input name `image`, float32, shape `[batch, 3, 224, 224]`, dynamic batch;
   - output name `logits`, float32, shape `[batch, 3]`;
   - opset compatible with onnx 1.22 / onnxruntime 1.28;
   - no custom ops; preprocessing remains Pillow/NumPy outside the graph.
2. Require PyTorch↔ORT parity on synthetic and representative private crops:
   argmax agreement, routed-outcome agreement, absolute logit tolerance ~1e-4.
3. Set `release_status`:
   - `production_candidate` only when Task B safety gates, parity, and verifier
     all pass;
   - otherwise `evaluation_only` or no package;
   - never `released` in Task B.
4. Commit the verified ONNX package under `models/handwriting_classifier/` only
   after privacy/security review of the derived artefact; never commit private
   manifests, checkpoints, or ImageNet caches.

## Consequences

- Task B may produce a package ready for Task C integration without enabling the
  router.
- Package notes distinguish OOF prototype diagnostics from the final fitted
  model (no independent held-out claim).

## Related

- ADR 0048, ADR 0050, ADR 0054–0057
