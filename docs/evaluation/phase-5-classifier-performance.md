# Phase 5 classifier performance

## Scope

CPU-oriented notes from Task B / B2 / B3 model-development runs.
**No GPU runtime claims.**

## Training device

- Locked dependency wheels: `torch==2.6.0+cpu`, `torchvision==0.21.0+cpu`

## Task B2 baseline (three-class)

- LOSGO: 3 configurations × 6 folds; wall clock ≈ **38 minutes**
- No production package published

## Task B3 dual-risk

LOSGO wall clock on this host (CPU):

| Config | Elapsed (s) |
|--------|------------:|
| dual_risk_weighted_bce | ≈ 912 |
| dual_risk_asymmetric_bce | ≈ 871 |
| dual_risk_focal | ≈ 831 |
| **Total train-export** | ≈ **2630** (~44 min) |

No `production_candidate` package was published (safety gate failed), so
production ORT load / warm-inference package benchmarks were not recorded for
B3. Unit-test dual-risk fixture continues to exercise CPU ORT session paths.

## Privacy

Benchmarks and reports use aggregate timings only; no document text logs.
