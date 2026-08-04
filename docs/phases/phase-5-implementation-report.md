# Phase 5 implementation report

**Status:** Phase 5 in progress — supplemented classifier remains below the routing safety gate.

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

### Task A — Prototype label sample (completed labelling)

- ADR 0053: single-pass ~300-crop prototype path; dual review / 45k / coverage
  correction parked as release hardening
- Queue: `phase5-prototype-primary-v1` (seed 4101) from existing 600-crop pilot
- Labels: printed 221, handwritten **0**, uncertain 54, non_text 23, excluded 2
- Status: **PROTOTYPE LABEL SAMPLE NEEDS EXPANSION** (missing handwritten class)
- **No** training; **no** OCR routing changes; **no** vision-provider calls

### Task A2 — Targeted handwriting seed collection (completed)

- Loopback seed UI + targeted page queue (uncertain pages, coverage worklist,
  police_form, form heuristics)
- Human-confirmed `human_confirmed_handwriting_seed` records; prior prototype
  review events were not mutated
- Aggregate readiness: `docs/evaluation/phase-5-handwriting-seed-readiness.md`
- Status: **PROJECT HANDWRITING SEED READY** (55 canonical seeds; external
  supplement still recommended; below ~100 target but enough to attempt
  prototype training)
- **No** training; **no** OCR routing changes; **no** vision-provider calls

### Task B — Prototype ONNX classifier train/evaluate/export

- `model-dev` stack: torch 2.6.0, torchvision 0.21.0, onnxscript (dev-only)
- Isolated tooling: `model_development/handwriting_classifier/`
- Project-only fit set: printed 221, handwritten 55, non_text 23; uncertain 54 challenge-only
- LOSGO OOF diagnostics across 6 source groups; ≤3 training configurations
- Prototype safety gate **not** met (handwritten→printed leak; safe-bypass <100%)
- Decision: **PROTOTYPE MODEL NEEDS SUPPLEMENTATION**
- Evidence: `docs/evaluation/phase-5-classifier-prototype.md` (+ FP/FN, performance)
- ADRs 0054–0058
- **No** production_candidate package; **no** OCR wiring; router remains disabled

### Task B2 — Handwritten ASAP supplementation

- NIST SD19 abandoned (unclear proprietary/derived-model terms)
- Handwritten ASAP (Zenodo 8088866, CC BY 4.0) via `pnpm phase5:model-data:asap:prepare`
- Public training-only; project LOSGO remains the safety gate
- ≤3 mixture configs: `asap_light`, `asap_medium`, `asap_medium_project_weighted`
- Cursive/signature slice gates (ADR 0062) in addition to Task B aggregate gates
- ADRs 0059–0062
- Decision: **SUPPLEMENTED MODEL STILL NOT SAFE FOR INTEGRATION**
  (HW→printed and signature→non_text remain; printed retention cannot clear
  with 100% safe-bypass)
- Evidence: `docs/evaluation/phase-5-classifier-prototype.md` (+ FP/FN, performance)
- **No** production_candidate package; **no** OCR wiring; router remains disabled
## Not done (later tasks — recovery path Tasks C–E)

- **C** Split Paddle detection from recognition and integrate classification
- **D** Prove routing invariants and corpus evaluation
- **E** Consolidate Phase 5 evidence and tag
- Release held-out freeze remains an explicit later decision (six-group adequacy)

Phase 5 is **not** passed.