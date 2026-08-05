# ADR 0060 — Handwritten ASAP CC BY 4.0 licence and provenance

## Status

Accepted (Phase 5 Task B2)

**Failed baseline — superseded for the current release path** (later B3/B4 eras also failed; release architecture is ADRs 0082–0087). No `production_candidate` classifier shipped.

## Context

Task B2 requires a clear licence before downloading public handwriting data or
committing a derived ONNX model.

Zenodo API record `8088866` (accessed 2026-08-04) reports:

| Field | Value |
|-------|--------|
| Title | Handwritten ASAP Short Answer Scoring |
| Creators | Gold, Christian; Zesch, Torsten |
| DOI | `10.5281/zenodo.8088866` |
| Record | https://zenodo.org/records/8088866 |
| Version | 1.0 (publication date 2020-07-01) |
| Licence | `cc-by-4.0` (Creative Commons Attribution 4.0 International) |
| Archive | `Handwritten-ASAP-SAS-V1.0.zip` (98397862 bytes) |
| Official checksum | `md5:d365ea3ca8afc19d4758a22daa2e1ea2` |

CC BY 4.0 permits commercial reuse and adaptations with attribution and
indication of changes.

## Decision

1. Treat CC BY 4.0 as sufficient for proprietary local model training and for
   committing a derived ONNX package under `models/handwriting_classifier/`,
   provided attribution and a modification notice are recorded.
2. Do **not** commit the raw archive, extracted images, or generated public
   crops; keep them under gitignored `model_development/.data/handwritten_asap/`.
3. Require prepare tooling to verify Zenodo licence id `cc-by-4.0`, refuse MD5
   mismatch, and record a local SHA-256 of the archive.
4. Required attribution (package README / model-record notes):

   > Gold, Christian; Zesch, Torsten (2020). Handwritten ASAP Short Answer
   > Scoring (Version 1.0) [Data set]. Zenodo.
   > https://doi.org/10.5281/zenodo.8088866
   > Licensed under CC BY 4.0
   > (https://creativecommons.org/licenses/by/4.0/).

5. Modification notice template: training subset and prepared crops were
   deterministically sampled, QC-filtered, and resized/letterboxed via
   `phase5-asap-crop-v1` from NIST-abandoned Handwritten ASAP sources on the
   recorded access date; transcription labels were discarded.

## Consequences

- Licence/checksum failure at prepare time stops Task B2 with
  `PUBLIC HANDWRITING SUPPLEMENT BLOCKED BY LICENSING`.
- Dependency and security docs must list this dataset as model-dev training
  data (not a runtime dependency).

## Related

- ADR 0059 (ASAP supplementation)
- https://creativecommons.org/licenses/by/4.0/
