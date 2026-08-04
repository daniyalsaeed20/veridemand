# ADR 0054 — MobileNetV3-Small transfer-learning baseline

## Status

Accepted (Phase 5 Task B)

## Context

Phase 5 needs a lightweight local writing-style classifier that outputs three
logits (`printed`, `handwritten`, `non_text`) for CPU ONNX Runtime inference.
The model must be small enough for region-level routing without becoming a
handwriting transcription (HTR) system.

## Decision

1. Use **MobileNetV3-Small** with ImageNet-pretrained
   `MobileNet_V3_Small_Weights.DEFAULT` from Torchvision.
2. Replace the classification head with a linear layer producing exactly three
   logits in fixed order: printed, handwritten, non_text.
3. Train with a two-stage transfer schedule: freeze features and train the head,
   then unfreeze the final feature blocks at a lower learning rate.
4. Keep Torch/Torchvision in the `model-dev` dependency group only; production
   inference remains ONNX Runtime + Pillow + NumPy.

## Consequences

- No transcription head, sequence decoder, or local HTR engine.
- Pretrained weight caches stay outside Git; startup never downloads weights.
- Architecture and weights provenance are recorded in `model-record.json`.

## Related

- ADR 0047 (three-class output + derived uncertainty)
- ADR 0048 (model package / preprocessing)
- ADR 0050 (ONNX Runtime boundary)
