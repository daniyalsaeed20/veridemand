# ADR 0055 — Project-only Task B training and conditional supplementation

## Status

Accepted (Phase 5 Task B)

**Failed baseline — superseded for the current release path** (later B3/B4 eras also failed; release architecture is ADRs 0082–0087). No `production_candidate` classifier shipped.

## Context

Task A produced prototype labels with zero handwritten examples. Task A2 added
55 human-confirmed project handwriting seeds across three source groups. Public
handwriting corpora (NIST SD19, EMNIST, IAM, etc.) could enlarge the handwritten
class, but importing them expands licence, privacy, and distribution scope.

## Decision

1. Task B trains **only** on project-reviewed labels:
   - printed / non_text from prototype-eligible reviews;
   - handwritten from active `human_confirmed_handwriting_seed` records;
   - deterministic synthetic **non-text** (Pillow/NumPy geometric patterns only).
2. Uncertain and excluded labels are never forced into the three model classes.
3. Do **not** download public handwriting datasets in Task B.
4. If no threshold set satisfies the Task B prototype safety gate, stop with
   `PROTOTYPE MODEL NEEDS SUPPLEMENTATION` and wait for a separate bounded
   supplementation task — do not auto-download data or wire the router.

## Consequences

- Prototype quality may be limited by 55 handwriting regions / three groups.
- Synthetic non-text is training-only and excluded from project OOF metrics.
- Live OCR integration remains Task C and requires a passing prototype gate.

## Related

- ADR 0053 (prototype annotation path)
- ADR 0051 (dataset / group-aware splits)
