# ADR 0059 — Handwritten ASAP public handwriting supplementation

## Status

Accepted (Phase 5 Task B2)

**Failed baseline — superseded for the current release path** (later B3/B4 eras also failed; release architecture is ADRs 0082–0087). No `production_candidate` classifier shipped.

## Context

Task B project-only training failed the prototype safety gate
(`PROTOTYPE MODEL NEEDS SUPPLEMENTATION`). ADR 0055 deferred public
supplementation. NIST Special Database 19 was evaluated and **abandoned**
because its Standard Reference Data / Special Database terms do not clearly
permit proprietary training and distribution of a derived ONNX package.

Handwritten ASAP Short Answer Scoring (Zenodo record 8088866) provides ~350
region-like handwritten answer crops under Creative Commons Attribution 4.0.

## Decision

1. Use **Handwritten ASAP Short Answer Scoring** as the sole public handwriting
   training supplement for Task B2.
2. Do **not** download or use NIST SD19, EMNIST, IAM, or other corpora with
   unclear or restrictive terms.
3. Public ASAP images are training-only, labelled solely as `handwritten`.
   Transcription / ASAP score text is never used for HTR or as class labels.
4. Project source-group-isolated OOF diagnostics remain the safety gate;
   ASAP samples never enter project evaluation metrics.
5. Retain the 55 human-confirmed project handwriting seeds for cursive,
   signatures, and project acquisition quality.

## Consequences

- Model-development gains an explicit, licence-verified prepare command.
- ADR 0055 remains valid for Task B historical scope; Task B2 supersedes the
  “wait for supplementation” outcome with this authorised path.

## Related

- ADR 0055 (project-only Task B)
- ADR 0060 (CC BY 4.0 provenance)
- ADR 0061 (project eval with public training)
- ADR 0062 (cursive/signature slice gates)
