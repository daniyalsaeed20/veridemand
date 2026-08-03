# Phase 5 recovery audit — ChatGPT handoff

**Status:** PHASE 5 RECOVERY AUDIT COMPLETE  
**Audit HEAD:** `d946945` on `phase-05-handwriting-routing`  
**Base:** Phase 4 v2.1 `2e77590432f21ebda2cdcf4feb3f67aaefd45cea`  
**Date:** 2026-08-03  

**Purpose:** Give ChatGPT enough repository truth to write Cursor implementation
prompts for the **minimal remaining Phase 5 path** (Tasks A–E) without needing
repo access. Prefer parking overbuilt annotation gates over deleting valid work.

**Companion reading (scope authority):**

- `docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md` §13 and §31 Phase 5
- `docs/roadmap.md` Phase 5 only
- ADRs 0047–0052 under `docs/decisions/`
- `docs/architecture/phase-5-handwriting-router.md`

**Do not** ask Cursor to implement Phase 6 vision LLM, OpenAI transcription,
contact sheets, `9065` regression, final reading order, tables/forms, search,
exports, or local HTR.

---

## Instruction block for ChatGPT

Using this recovery audit as ground truth:

1. Adopt **Strategy 1** — continue from HEAD `d946945`; do not reset or branch
   from Task 2/3A.
2. Treat dual review, full-page coverage correction, six-group held-out freeze,
   and full 45k labelling as **parked / release hardening**, not mandatory
   blockers for a prototype router (unless the user overrides).
3. Draft **five** Cursor prompts (Tasks A–E) matching section M below.
4. Each prompt must include: objective, files likely to change, tests, stopping
   boundary, human involvement, explicit out-of-scope list, privacy rules, and
   git safety (no `git add .`, preserve unrelated worktree files).
5. Default decisions when the user has not chosen otherwise (section N).

---

## A. Repository state

| Item | Value |
|------|--------|
| Branch | `phase-05-handwriting-routing` |
| HEAD | `d946945` |
| Ancestry | Descends from Phase 4 v2.1 `2e77590`; Tasks 1–3D SHAs present |
| Diff since Phase 4 | 102 files, +12147 / −61 across 15 Phase 5 commits |
| Phase 5 tag | None |
| Unrelated worktree | Modified Phase 4 final report; untracked prior handoff/prompt docs — leave alone |

### Phase 5 commit chain (oldest → newest)

```text
86fe1f4 docs(phase5): audit handwriting routing integration
39f3b89 feat(phase5): add handwriting classifier contracts and runtime
3ba9742 test(phase5): verify classifier package and readiness
060884e docs(phase5): document classifier runtime foundation
0b7cede feat(phase5): add private crop dataset and labelling tooling
b3d1dc1 test(phase5): cover crop dataset export review split and privacy
8216cbb docs(phase5): document Task 3A dataset tooling and readiness
23ab68b fix(phase5): harden private crop population workflow
a883aff docs(phase5): record private review queue readiness
43fc8d0 fix(phase5): preserve crop provenance and coverage evidence
eb9c9d7 feat(phase5): add annotation pilot and coverage gate
17f2c0f test(phase5): validate pilot isolation and privacy
6a7a0e2 docs(phase5): document pilot review requirements
894a0de fix(phase5): harden page coverage review
d946945 docs(phase5): record human coverage audit
```

---

## B. Reality summary

Phase 5 has contracts, settings, an ONNX Runtime classifier service, package
verification, health integration, and a large offline private
crop/labelling/coverage toolchain, but **no trained production model**, **no
live routing**, and **no detect-before-recognise split**. Live processing still
runs combined Paddle `predict` and stamps `pending_phase_5`. **No handwritten or
uncertain region currently bypasses Paddle.**

Intended runtime (SoT / roadmap):

```text
detect → classify → printed→Paddle rec | handwritten/uncertain→reserve Phase 6 | non_text→suppress
```

---

## C. Commit classification (summary)

| SHA | Class | Role |
|-----|-------|------|
| `39f3b89`, `3ba9742` | CORE | Classifier contracts/runtime/tests/fixture |
| `86fe1f4`, `060884e`, docs commits | SUPPORTING | Design/docs |
| `0b7cede`…`d946945` dataset/pilot/coverage | SUPPORTING / OVERBUILT / HARDENING | Offline tooling; ADR 0052 gates stricter than SoT minimum |

**Divergence:** Tasks 3A–3D built release-grade annotation/coverage before
detect-split + train + wire routing.

---

## D. Deliverable matrix

| Deliverable | Status |
|-------------|--------|
| Labelled region dataset | PARTIAL (crops exist; 0 script labels) |
| Classifier architecture / ORT service / verifier | FOUNDATION ONLY / COMPLETE isolated |
| Trained weights / production ONNX | NOT STARTED / synthetic fixture only |
| Detect-before-recognise + live routing + bypass invariants | NOT STARTED |
| Evaluation / FP-FN / approved recall / exit evidence | NOT STARTED |

---

## E. OCR call graph and insertion points

Sole live inference: `PaddleOcrAdapter.recognise` → `PaddleOCR.predict` (combined)
in `backend/app/extraction/visual/paddle_adapter.py`, used by
`worker.process_page` and repair crop callbacks (`recognise_only` is a misnamed
combined-predict wrapper).

| Runtime path | Det separate? | Geometry before rec? | Classifier insert | Refactor? |
|---|---|---|---|---|
| Full-page primary / fallbacks | No | No | After detect before printed rec | **Yes** |
| Repair recognition-only | No | Yes (native) | Before crop callback | Gate |
| Repair local det+rec | No | Region bbox | Before/after crop predict | Prefer det→classify |
| Digital native / embedded verified | N/A | N/A | N/A | No |

---

## F. Paddle capability

| Item | Finding |
|------|---------|
| Pins | paddleocr 3.7.0, paddlepaddle 3.3.0, paddlex 3.7.2 (transitive) |
| App today | Combined `predict` only |
| Feasible split | PaddleX `create_model("PP-OCRv6_medium_det|rec")` each has `predict` |
| Rule | Do **not** add a second detector unless existing Paddle models cannot split |

---

## G. Classifier foundation

- Package: `backend/app/extraction/handwriting_router/`
- Call: `HandwritingClassifierService(settings).classify_crop(image, ...)`
- Defaults: `HANDWRITING_ROUTER_ENABLED=false` (Phase 4 preserved)
- Thresholds (provisional): printed 0.85, handwriting 0.70, non_text 0.80, margin 0.10
- Deps: onnxruntime 1.28.0 MIT (core); onnx 1.22.0 Apache-2.0 (model-dev); no torch
- `models/handwriting_classifier/` = README only; live stamp still `pending_phase_5`

---

## H. Dataset reality (aggregates only)

| Metric | Count |
|--------|------:|
| Source groups / documents / pages | 6 / 6 / 215 |
| Crop records / canonical | 65,649 / 44,951 |
| Pilot | 600 |
| Script labels | 0 |
| Coverage complete / correction worklist | 205 / 10 |
| Splits / held-out / training authorised | absent / false / false |

**Provenance:** 100% `full_page_ocr` from combined Paddle det+rec geometry.
Empty-text dropped; low-confidence non-empty retained; signatures/missed
handwriting likely underrepresented. Prototype training possible with known
bias; full coverage correction not a hard prerequisite for a first model.

Privacy: never put private paths, filenames, page/crop IDs, visible text, or
reviewer IDs in prompts or commits.

---

## I. Tooling keep / park

| Keep on critical path | Park / defer |
|----------------------|--------------|
| Contracts, settings, handwriting_router, health, dependency boundary | Dual pilot, adjudication, full-queue auth |
| Basic export, backup, verify, simple labeler | Split/held-out freeze until labels exist |
| | Coverage correction as release hardening (optionally fix 10 pages first) |
| | Six-group adequacy = **release** freeze gate, not prototype blocker |

Prefer park over delete. Nothing must be reverted for runtime safety (tools are
offline; not imported by FastAPI production).

---

## J. Training readiness

Missing: torch (or approved framework), MobileNetV3-Small (or approved) arch,
dataloaders, augmentation, train loop, balancing, checkpoints, calibration,
ONNX export, PyTorch↔ONNX parity, production package writer. Only synthetic
fixture generator exists.

---

## K. Tests

~75 Phase 5 tests for classifier/dataset/pilot/coverage/privacy/boundary.
Non-wiring tests assert classifier is **disconnected**.
**Missing:** handwritten/uncertain never enter Paddle; printed reaches Paddle;
integrated classify→router→OCR tests.

---

## L. Recovery strategy

**Recommended: Strategy 1 — continue from `d946945`.**  
Do not reset to Task 2/3A. Park overbuilt gates operationally; implement core
feature forward.

---

## M. Minimal remaining tasks (prompt targets)

### Task A — Practical labelled sample

- Objective: obtain ~200–300 trusted script labels (or single-pass 600) via
  existing loopback labeler; optional cheap fix of 10 coverage worklist pages.
- Human: required for labels.
- Out of scope: full 45k review, dual review, training, OCR wiring.

### Task B — Train / evaluate / export classifier

- Objective: add model-dev training stack; train 3-class model; export ONNX
  package under `models/handwriting_classifier/`; parity tests.
- Out of scope: live OCR wiring.

### Task C — Split Paddle + integrate classification

- Objective: detect (PaddleX model-level or equivalent) → classify → recognise
  printed only; gate repair crops; router remains default-off until proven.
- Files: `paddle_adapter.py`, visual worker, repair methods, settings/health.
- Out of scope: Phase 6 vision LLM.

### Task D — Routing invariants + corpus evaluation

- Objective: automated no-Paddle for handwritten/uncertain; printed reaches
  Paddle; FP/FN report; provisional recall target.
- Out of scope: release held-out freeze without explicit decision.

### Task E — Evidence + tag

- Objective: consolidate Phase 5 exit evidence; tag only when gates agreed.
- Out of scope: Phase 6/7.

---

## N. Default decisions (use unless user overrides)

1. Label sample: **B then expand** (200–300, then more if needed).
2. Licensed public/synthetic data for prototype balance: **Yes**, with licence
   recording.
3. Prototype recall: document provisional; calibrate after Task D.
4. Continue from `d946945`: **Yes**.
5. Coverage correction before labelling: **Park**; optionally fix 10 worklist
   pages first if cheap.
6. Six-group rule: **release freeze only**, not prototype training ban.

---

## O. Risks

- Detect/rec split may change Phase 4 OCR quality/timing.
- Dataset misses handwriting Paddle never boxed.
- Overbuilt gates can stall core feature if treated as mandatory.
- Enabling router with provisional thresholds is unsafe.
- No training stack yet — schedule risk.
- Repair “recognition-only” still runs combined predict on crops.

---

## P. Audit validation snapshot

| Check | Result |
|-------|--------|
| `uv lock --check` | pass |
| dependency boundary / private corpus guard | pass |
| ruff on phase5 paths | pass |
| pytest collect | 556 tests |
| contracts check | skipped during audit (would regenerate) |

---

## Q. Change confirmation (audit itself)

The recovery audit was read-only regarding private corpus and OCR runtime.
This handoff document is the durable ChatGPT input artifact.

```text
PHASE 5 RECOVERY AUDIT COMPLETE
```
