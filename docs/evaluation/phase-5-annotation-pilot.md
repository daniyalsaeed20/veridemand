# Phase 5 annotation pilot

**Status:** DUAL PILOT QUEUES READY — PARKED FOR RELEASE HARDENING (ADR 0053)

Default Task A human path is the single-pass prototype queue
(`phase5-prototype-primary-v1`); see `docs/operations/phase-5-labelling.md`.

- Pilot version: `phase5-annotation-pilot-v1`
- Sampling policy: `phase5-annotation-pilot-sampling-v1`
- Pilot crop count: **600**
- Target size: **600**
- Pages represented: **215**
- Source groups represented: **6**
- Per-page min/max: **1** / **7**
- Primary seed: `3101`
- Secondary seed: `3102`
- Pilot manifest SHA-256: `b35d89c2022eadfbccf058b86a9cbea64efea1f6e13ebb64033fedb412a225e5`
- Primary queue SHA-256: `f6d1e7be60cdcc4ff4931ba0c13d3c3d3e71a93eec17c017072391efcafa2080`
- Secondary queue SHA-256: `30c66b15a7e6c755cb7149a241057ab26d80befceb309e3c9f573e0d4a73da9e`
- Membership equal: **True**
- Ordering different: **True**
- Full queue authorised: **False**
- Human labels assigned in this task: **0**

## Candidate-source representation (selection metadata only)

- `full_page_ocr`: 600

## Policy

- Dual `pilot-primary` / `pilot-secondary` review remains available for release
  hardening but is **not** required before prototype model development (ADR 0053).
- Full primary queue remains preserved but unauthorised until explicit approval.
- Candidate provenance and sampling reasons are never shown to reviewers.
- No training, splits, or held-out freeze are authorised by this dual pilot alone.
- Source-group adequacy: see `docs/evaluation/phase-5-source-group-adequacy.md`.
- Operator steps: `docs/operations/phase-5-labelling.md`.
- ADR 0052 (dual pilot / coverage gate); ADR 0053 (prototype path).
