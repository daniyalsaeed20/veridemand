# Phase 5 classifier performance (Task B2)

## Scope

CPU-oriented notes from Task B2 ASAP-supplemented model-development runs.
**No GPU runtime claims.** No production package was published (safety gate
failed).

## Training device

- Locked dependency wheels: `torch==2.6.0+cpu`, `torchvision==0.21.0+cpu`
- Host has a GTX 1060, but CPU wheels were used for cross-platform lock
  reproducibility
- 4 logical CPUs

## Training throughput (approximate)

- ASAP prepare: ~3 minutes download+extract+subset (98.4 MB archive; 350 crops)
- LOSGO: 3 configurations × 6 folds; wall clock ≈ **38 minutes** for full
  Task B2 train-export search on this host (includes threshold grid search)
- Public handwriting adds 150–350 train-only images per fold; synthetic
  non-text remains 300

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
