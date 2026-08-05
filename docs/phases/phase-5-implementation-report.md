# Phase 5 implementation report

**Status:** Phase 5 in progress — detector-first shadow pipeline established; router model must be retrained on detector-first regions before live integration.

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

### Task B3 — Safety-first dual-risk classifier

- Replaced forced three-class softmax with shared MobileNetV3-Small + two
  independent risk logits (`handwriting_risk`, `non_text_risk`)
- Targets: printed→[0,0], handwritten→[1,0], non_text→[0,1]; uncertain challenge-only
- Losses (≤3): weighted BCE, asymmetric HW-FN×3.0, binary focal
- ASAP medium (350) + synthetic non-text (300) training-only; project LOSGO gates
- Safety-first decision policy: printed only when both risks safely low;
  material handwriting never discarded as non_text; conflicts → uncertain
- Package schema v2: `risk_logits` `[batch,2]`, `independent_binary_risk_logits`
- ADRs 0063–0067; ADRs 0047 / 0054 / 0058 marked superseded for production-candidate evaluation
- Three-class baseline retained as **prototype baseline — superseded for safety evaluation**
- Decision: see `model_development/.artifacts/task_b3_decision.json`
  → **`SAFETY-FIRST MODEL STILL NOT SAFE`**
  (focal clears HW leaks only with printed retention ≈19%; weighted/asymmetric
  still leak HW→printed/non_text)
- **No** production_candidate package; **no** OCR wiring; router remains disabled; **no** Phase 6/7

### Task B4 — Route-first vision-reservation classifier

- Replaced dual-risk heads with `vision_required` + `handwriting_present`
- Uncertain (54) is a `vision_required` training positive with HW loss masked
- Non-text remains unsafe for Paddle but the model never emits `non_text`
- Losses (≤3): weighted BCE, asymmetric vision FN, focal on route head
- ASAP medium (350) + synthetic non-text (300) training-only; project LOSGO gates
- Decision policy: printed only below `local_ocr_safe`; handwritten when route
  and HW accept; else uncertain
- Package schema v3: `route_logits` `[batch,2]`, `route_first_independent_logits`
- ADRs 0068–0071; B/B2/B3 retained as failed baselines
- Decision: see `model_development/.artifacts/task_b4_decision.json`
  → **`ROUTE-FIRST MODEL STILL NOT SAFE`**
  (focal clears HW/uncertain→printed only with printed retention ≈14%;
  weighted/asymmetric still leak or fail retention)
- **No** production_candidate package; **no** OCR wiring; router remains disabled; **no** Phase 6/7

### Task C0 — Detector-first shadow pipeline and region corpus

- Separate PaddleX create_model det/rec APIs on configured PP-OCRv5_mobile_*
  local assets (detect_text / 
ecognise_text_crops)
- Live Phase 4 combined PaddleOCR.predict path unchanged; shadow default off
  (PHASE5_DETECT_FIRST_SHADOW_ENABLED=false)
- Offline corpus: phase5-detector-first-regions-v1 via
  pnpm phase5:detector-corpus:build|compare|coverage
- Every detection retained before recognition (empty/failed/low-confidence kept)
- Strict label transfer; handwriting-seed detector coverage aggregates
- ADRs 0072–0076; architecture/eval/ops/security docs updated
- **No** classifier training; **no** live routing; **no** Phase 6

## Not done (later tasks — recovery path Tasks C–E)

- **C** Integrate classification into detect→classify→printed-recognise (after
  router retraining on detector-first crops)
- **D** Prove routing invariants and corpus evaluation
- **E** Consolidate Phase 5 evidence and tag
- Release held-out freeze remains an explicit later decision (six-group adequacy)

Phase 5 is **not** passed.
