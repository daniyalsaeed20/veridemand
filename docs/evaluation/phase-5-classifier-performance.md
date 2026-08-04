# Phase 5 classifier performance (prototype)

## Scope

CPU-oriented notes from Task B model-development runs. **No GPU runtime claims.**
No production package was published (safety gate failed).

## Training device

- Locked dependency wheels: `torch==2.6.0+cpu`, `torchvision==0.21.0+cpu`
- Host has a GTX 1060, but CPU wheels were used for cross-platform lock
  reproducibility
- 4 logical CPUs

## Training throughput (approximate)

- ~1 minute per LOSGO fold (stage1=3 + stage2=5 epochs, batch 16, ~300 synthetic
  non-text + project fold train set)
- 3 configurations × 6 folds ≈ 18 fold trainings completed on CPU

## Package / inference

Not applicable for a committed `production_candidate` package.

When an ONNX package is later produced, benchmark via
`HandwritingClassifierService` + `CPUExecutionProvider` and record:

- model / package size
- session creation time
- first inference latency
- warm single-crop latency
- warm batch latency / throughput
- peak memory where practical

## Privacy

Benchmarks and reports use aggregate timings only; no document text logs.
