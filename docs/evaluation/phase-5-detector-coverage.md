# Phase 5 — Detector coverage of handwriting seeds

## Purpose

Measure whether the detector-first pipeline boxes the **55**
human-confirmed handwriting seed geometries. A handwriting region the detector
misses cannot be routed by the Phase 5 classifier.

This is a **detection** measurement — not recognition, and not classification.

## Method

For each active seed bbox, classify privately against detector-first regions on
the same page:

| Kind | Meaning |
|------|---------|
| exact / near_exact | high IoU with a single detector box |
| contained | a larger detector box covers the seed |
| fragmented | multiple overlapping fragments |
| missed | no sufficient overlap |

Command:

```text
pnpm phase5:detector-corpus:coverage
```

## Aggregate results (full private detector-first corpus)

| Metric | Value |
|--------|------:|
| Handwriting seed total | 55 |
| Handwriting seed detected count | 36 |
| Handwriting seed detection recall | 0.655 |
| Contained | 30 |
| Fragmented | 6 |
| Missed | 19 |
| Digits recall | 0.50 |
| Hand-print recall | 1.00 |
| Cursive recall | 0.545 |
| Signature recall | 0.636 |
| Longer-note recall | 1.00 |

## Limits (do not hide)

- **19 / 55** handwriting seeds have **no** matching detector region.
- Cursive and signature recalls are incomplete; those misses cannot be
  routed by a Phase 5 classifier until detection coverage improves.
- Task C0 does **not** add a second handwriting-specific detector.
- Committed reports contain aggregates only — no private page/seed IDs.
