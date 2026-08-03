# Phase 5 implementation report

**Status:** Phase 5 in progress — recovery audit complete at `d946945`.
Classifier foundation exists but is unwired; annotation/coverage tooling is
parked for prototype path. No production model; no live handwriting routing.

See `docs/phases/phase-5-recovery-audit.md` for ChatGPT handoff and Tasks A–E.

## Completed

### Task 1 — Preflight audit

Evidence-based design freeze in `docs/phases/phase-5-preflight-audit.md`.

### Task 2 — Classifier runtime foundation

- Contracts: lifecycle / outcome / decision reason / inference source / evidence
- Settings: router disabled by default; required/optional distinction; provisional thresholds
- Dependency: CPU `onnxruntime`; `onnx` in `model-dev`; boundary allowlists
- Model package verifier + reusable `HandwritingClassifierService`
- Health/readiness integration for `handwriting_classifier`
- Unit tests, ADRs 0047–0050, architecture/ops/security docs
- **Not** wired into Phase 4 OCR worker or repair recognition paths
- **No** production ONNX model committed

### Task 3A — Private crop dataset and labelling workflow

- Schemas/tooling under `backend/app/datasets/phase5/` (no production OCR imports)
- Private root `fixtures/private/phase5/` + privacy guard allowlist for README only
- Crop export / manual import / verify CLIs; loopback labeler; resolve; group-aware split
- ADR 0051; dataset + labelling ops docs
- **No** training, ONNX export, or live classifier wiring

### Task 3B — Private crop corpus population and primary queue

- Source registration from approved private batch manifest (opaque IDs)
- Offline page render + geometry populate (gitignored); crop export; duplicates; verify
- Blinded full primary-review queue (preserved; not default for humans after 3C)
- **No** fabricated human labels; **no** train/val/held-out splits; **no** training

### Task 3C — Coverage audit and annotation pilot

- Provenance audit: private crops are correctly `full_page_ocr` (lines); repair empty;
  blocks are 1:1 line proxies intentionally skipped by export-all
- Source-manifest dedupe migration (`586 → 215` unique page rows)
- Block-coverage audit + page overlay coverage queue (215 pages)
- Deterministic 600-crop dual pilot queues (seeds 3101 / 3102)
- Labeler requires explicit `--queue`; full-primary needs `--authorise-full-queue`
- Source-group adequacy: **INSUFFICIENT FOR RELEASE EVALUATION**
- ADR 0052
- Status: **PILOT REVIEW QUEUES READY — HUMAN PILOT REQUIRED**
- **No** private human labels created by tooling; **no** training; **no** OCR routing changes

### Task 3D — Human page-coverage review

- Human review of all 215 page overlays via loopback coverage UI
- Aggregate report: `docs/evaluation/phase-5-coverage-review.md`
- Decision updated by ADR 0053: **COVERAGE CORRECTION PARKED** for prototype path
  (10 worklist entries remain; excluded from prototype queue sample)
- Private correction worklist generated from human outcomes (gitignored)
- **No** crop script labels from Task 3D; **no** training

### Task A — Prototype label sample (in progress)

- ADR 0053: single-pass ~300-crop prototype path; dual review / 45k / coverage
  correction parked as release hardening
- Queue: `phase5-prototype-primary-v1` (seed 4101) from existing 600-crop pilot
- Default serve: `prototype-primary` with opaque `proto_reviewer_*` / `rev_*`
- **No** training; **no** OCR routing changes; **no** vision-provider calls

## Not done (later tasks — recovery path Tasks B–E)

- **B** Train / evaluate / export lightweight ONNX classifier
- **C** Split Paddle detection from recognition and integrate classification
- **D** Prove routing invariants and corpus evaluation
- **E** Consolidate Phase 5 evidence and tag
- Release held-out freeze remains an explicit later decision (six-group adequacy)

Phase 5 is **not** passed.
