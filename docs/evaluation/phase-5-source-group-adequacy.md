# Phase 5 source-group adequacy

**Conclusion:** `SOURCE-GROUP COVERAGE INSUFFICIENT FOR RELEASE EVALUATION`

Six groups do **not** block prototype training or integration (ADR 0053). They
do block a strong **release** generalisation / held-out freeze claim until
adequacy improves or an explicit later decision records provisional acceptance.

Generated for Task 3C (aggregate / opaque only). No private identifiers.

## Current coverage

| Metric | Value |
|--------|------:|
| Independent source groups | 6 |
| Registered documents | 6 |
| Pages with geometry | 215 |
| Canonical crops (exact-dedup) | 44,951 |

### Broad family coverage (documents)

After privacy redaction of singleton strata in readiness reports, families appear
as mixed `billing_ledger` / `other` aggregates. Unredacted tooling observes
multiple broad families among the six groups, but **several families are still
represented by only one source group**.

### Diversity that is not yet known

- Handwriting style diversity: **unknown** (no human labels yet)
- Writer diversity: **unknown**
- Template diversity beyond the six registered groups: **limited / unknown**
- Non-sensitive acquisition device/date diversity: **not established**

### Duplicate-family relationships

Exact multi-member duplicate families exist (~3,285). Exact duplicates are
canonicalised for queues/pilot. Perceptual near-duplicates are warnings only and
are moderated in pilot sampling (representative + small pair sample).

### Overfitting risk

With one document per source group and only six groups, group-aware splits can
still leak template/writer correlation into held-out evaluation. Freezing a
release held-out set now would overstate generalisation.

## Held-out freeze authorisation

**Not authorised.** No explicit project decision accepts the six-group
limitation for release evaluation. ADR 0052 prohibits freeze until adequacy
improves or an explicit recorded approval exists.

## Acquisition priorities (non-sensitive plan)

Do not auto-collect private documents. Prefer additional **independent** groups:

1. More than one document group per broad source family (police, medical,
   billing, fax/image, insurance/letter controls)
2. Independent form instances / templates
3. Different handwriting styles and writers where legally available
4. Different scanners / image qualities
5. Faint handwriting, handwritten digits, cursive, hand-printed capitals
6. Signatures with local geometry
7. Clean printed controls and non-text false detections

No hard release count is prescribed here; size follows later evidence-based
decision after pilot review and additional acquisition.

See ADR 0052, ADR 0053, and `docs/evaluation/phase-5-annotation-pilot.md`.
