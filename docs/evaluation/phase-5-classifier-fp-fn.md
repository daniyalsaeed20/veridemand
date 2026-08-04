# Phase 5 classifier FP/FN categories (prototype)

Privacy-safe aggregate categories from source-group-isolated out-of-fold
predictions. **No crop IDs, paths, text, or screenshots.**

## Decision context

`PROTOTYPE MODEL NEEDS SUPPLEMENTATION` — safety gate not met; counts below are
diagnostic for the best Pareto configuration (`balanced_sampler_default_aug`
argmax + near-best abstention candidates).

## Routing / confusion categories (aggregate)

| Category | Approximate count |
|----------|------------------:|
| handwritten routed / predicted printed | 11–24 |
| handwritten routed / predicted non_text | 8–11 |
| printed routed / predicted handwritten | 11–17 |
| printed routed uncertain (high-threshold candidates) | ~50–140 |
| non_text routed / predicted printed | 0–6 (0 under best threshold candidates) |

## Handwriting subtype confusion (seed category tags, opaque)

When seed category metadata was available on OOF handwritten rows:

| Category | Observation |
|----------|-------------|
| signatures confused | present among handwritten misses |
| handwritten digits confused | present among handwritten misses |
| cursive confused | present among handwritten misses |

Exact per-subtype counts vary by fold support; several held-out groups contain
no handwritten examples.

## Geometry / quality categories

| Category | Observation |
|----------|-------------|
| small crops | some misroutes among low-area crops |
| broad crops | some misroutes among high aspect-ratio line crops |
| low-resolution crops | residual risk (seed + prototype crops) |
| mixed-content crops | not separately labelled; residual risk |

## Interpretation

The dominant safety failure is **handwritten regions scoring as printed with
very high confidence** on held-out source groups. Abstention cannot eliminate
all leaks without destroying printed retention. This supports project-data
supplementation rather than threshold loosening.
