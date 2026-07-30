# ADR 0051 — Phase 5 human-label crop dataset and group-aware splits

## Status

Accepted (Phase 5 Task 3A)

## Context

Phase 5 handwriting style classification needs a private, human-labelled crop
dataset before any training or ONNX export (Task 3B+). OCR text, heuristic
scores, and filenames must never become ground truth. Private case material
must never be committed.

## Decision

- Store private material only under `fixtures/private/phase5/` (gitignored except
  `README.example.md`).
- Human labels are exactly: `printed`, `handwritten`, `uncertain`, `non_text`.
- Signatures are labelled `handwritten` (labeler key `S` maps to handwritten).
- `uncertain` is challenge / vision-reserved and **not** training-eligible for
  the initial 3-class model (`printed` / `handwritten` / `non_text`).
- Training eligibility requires agreed double-review or adjudication.
- Splits are group-aware on `source_group_id` + `duplicate_family_id` with a
  versioned algorithm and seed; identical inputs → identical manifests.
- Exact SHA-256 duplicates share a `duplicate_family_id`; perceptual near-dups
  emit warnings only.
- Held-out freeze is **explicit only** (`phase5:dataset:freeze-heldout`) and
  requires agreed/adjudicated labels; Task 3A does not auto-freeze private data.
- Labelling UI is a loopback-only stdlib server under `scripts/phase5/`; it is
  not mounted in production FastAPI and not shipped in the frontend bundle.
- No new production dependencies for Task 3A (Pillow / NumPy / stdlib only).

## Consequences

Dataset tooling can reach `DATASET TOOLING READY — HUMAN LABELLING REQUIRED`
with truthful zero counts until humans label private crops. Task 3B training
must consume resolved labels and frozen splits from this workflow only.
