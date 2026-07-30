# Phase 5 preflight audit — handwriting detection and routing

**Task:** Phase 5 Task 1 (analysis, documentation, and design freeze only).  
**Date:** 2026-07-31  
**Branch:** `phase-05-handwriting-routing`  
**Baseline HEAD at audit start:** `2e77590432f21ebda2cdcf4feb3f67aaefd45cea`  
**Authority:** current repository code and generated contracts → ADRs / Phase 4 Corrections 1–7 → living docs → frozen Source of Truth → roadmap.

This document does **not** implement the ONNX classifier, add dependencies, modify production contracts, alter Phase 4 behaviour, train a model, or begin Phase 6/7.

---

## 1. Executive summary

Phase 4 is a valid Phase 5 starting point: HEAD is exactly the v2.1 route-accounting commit, and tags `phase-4-visual-detection-printed-ocr-v2` / `v2.1` are present.

Phase 5 handwriting routing is **scaffolding only** today: README stubs under `backend/app/extraction/handwriting_router/` and `models/handwriting_classifier/`; a single-value `HandwritingAssessment.pending_phase_5` contract; reserved but unused settings; health always reports `handwriting_classifier` as `not_configured`.

The critical integration finding is that **full-page printed OCR combines detection and recognition in one `PaddleOCR.predict()` call** (`PaddleOcrAdapter.recognise`). Stable detector geometry and recognition text appear together; crops are not created on the main full-OCR path. Phase 5 therefore requires a **minimal detect-then-classify-then-recognise-printed-only split** of that combined call — not a second detector, not a whole-page classifier, and not replacement of exclusive page terminal routes.

There is **no human-labelled crop dataset** suitable for training or for a learned `uncertain` class. Recommend **Option A**: ONNX outputs `printed` / `handwritten` / `non_text`; runtime derives public `uncertain` by deterministic abstention. There is **no approved handwriting safe-bypass recall threshold** in the repository; Phase 5 cannot be declared passed until humans approve one via ADR/evaluation. Keep the overall progress cap at **65%**.

---

## 2. Phase authority and superseded SoT values

| Layer | Role |
|-------|------|
| Current code + generated contracts | Behaviour already implemented |
| `docs/decisions/` ADRs 0017–0046 + Corrections 1–7 | Supersede outdated SoT implementation numbers |
| Living docs under `docs/architecture/`, `docs/phases/`, `docs/evaluation/`, `docs/operations/`, `docs/security/`, `docs/dependencies/` | Calibrations and evidence |
| `docs/SOURCE_OF_TRUTH.md` ≡ `docs/VeriDemand_Document_Extraction_Source_of_Truth_v1.0.md` | Frozen doctrine only (neither edited by this task) |
| `docs/roadmap.md` | Phase sequencing |
| README summaries | Lowest priority |

**SoT values superseded by Phase 4 reality (do not restore):**

| SoT claim | Current reality |
|-----------|-----------------|
| 300 DPI / 400 retry | 200 DPI default + adaptive source resolution (ADR 0017/0023) |
| PP-OCRv5 as sole model story | Settings default `PP-OCRv5_mobile_*` (ADR 0023); calibrated history includes v6 |
| Progress stage model to 100% | Hard overall cap **65%** (`OVERALL_CAP`, `MAX_PHASE4_PROGRESS_PERCENT`) |
| Page `*_authority` modes as terminals | Exclusive terminals: `digital_native`, `embedded_ocr_verified`, `embedded_ocr_targeted_repair`, `full_visual_ocr`, `visual_no_text`, `page_failed` + `final_route_histogram` |
| OpenCV / Structure / ONNX / OpenAI in app | Pillow+NumPy; no ONNX/OpenAI yet; boundary forbids `onnxruntime`/`openai`/`cv2` |
| FIFO-ish queue | Fair WRR + aging + page quantum (Correction 7) |
| GPU language | CPU-only acceptance baseline |

Doctrine that still binds: least-expensive reliable source; native text never auto-trusted; **no dedicated local HTR**; LLM never invents coordinates; coordinates normalised `[0,1]` top-left; runtime-only sessions.

---

## 3. Git baseline

| Item | Value |
|------|-------|
| Starting branch | `fix/phase-4-exclusive-route-histograms` |
| Audit branch | `phase-05-handwriting-routing` (created from HEAD) |
| Starting / branch HEAD | `2e77590432f21ebda2cdcf4feb3f67aaefd45cea` |
| Ancestor of v2.1 commit | Yes (HEAD **is** that commit) |
| Tag `phase-4-visual-detection-printed-ocr-v2` | Present |
| Tag `phase-4-visual-detection-printed-ocr-v2.1` | Present |
| Remote | `origin` → `https://github.com/daniyalsaeed20/veridemand.git` |

**Preserved unrelated worktree files (not part of this commit):**

- Modified: `docs/phases/phase-4-final-implementation-report.md`
- Untracked: `docs/phases/phase-5-chatgpt-handoff-audit.md`, `docs/phases/phase-5-cursor-implementation-prompt.md`

No Phase 5 release tag created. No hard reset, force-push, or Phase 4 tag rewrite.

---

## 4. Current Phase 4 architecture relevant to Phase 5

**Actual package layout (no `printed_ocr/` directory):**

| Area | Path |
|------|------|
| Visual OCR worker / adapter / render / preprocess / noise / quality | `backend/app/extraction/visual/` |
| Hybrid routing, embedded coverage, targeted repair | `backend/app/extraction/routing/` |
| Scheduling / progress | `backend/app/processing/` |
| Handwriting stub | `backend/app/extraction/handwriting_router/README.md` only |
| Classifier model stub | `models/handwriting_classifier/README.md` only |

**Verified Phase 4 behaviours still in force:**

- Rendering: `pypdfium2` via `backend/app/extraction/visual/renderer.py` (`render_page`)
- Printed OCR: Paddle via `PaddleOcrAdapter` (`paddle_adapter.py`); models `PP-OCRv5_mobile_det` / `PP-OCRv5_mobile_rec` in local `.models/paddleocr/model-record.json`
- DPI: settings-driven 200 + adaptive (ADR 0023)
- Native trust gate → hybrid `PageRouter.decide` → exclusive page terminals
- Embedded OCR verification + targeted repair + dense-form quality gate
- Fair WRR / aging / page quantum (`fair_ocr_page_quantum`, default 2)
- Progress capped at 65% (`backend/app/processing/progress_weights.py` `OVERALL_CAP`; `backend/app/contracts/documents.py` `MAX_PHASE4_PROGRESS_PERCENT`)
- Runtime-only sessions; Pillow + NumPy (no app `cv2`); CPU baseline
- `final_route_histogram` exclusive page accounting (v2.1)

**Phase 5 must not replace page terminals with handwriting page routes.** Classification is region-level evidence subordinate to existing page accounting.

---

## 5. Recognition call graph

### Cross-cutting answers

| Question | Finding |
|----------|---------|
| Detection vs recognition | **Combined** on full-page path: one `PaddleOCR.predict()` in `PaddleOcrAdapter.recognise`. Repair helpers `recognise_only` / `detect_and_recognise_crop` still call combined predict on crops. |
| Stable geometry first exists | Full OCR: `RawOcrLine.polygon_px` in `PaddleOcrAdapter._adapt` (from `rec_polys` / `dt_polys`). Normalised geometry in `worker._build_contract_lines` via `map_pixel_polygon`. Repair: native `NativeWord.geometry` → `RepairRegionRecord` in `repair_clustering.cluster_failed_boxes`. |
| Crops created | **Not** on full-page OCR. Spot-check: `recognition_check.crop_word_region`. Repair: `repair_methods._crop_image`, `targeted_repair.crop_region`. |
| Region IDs | Lines/words: `ocrline_p{page}_{idx}` / `ocrword_p{page}_{seq}` in `worker._build_contract_lines`, `materialise_embedded`, `repair_reconcile`. Repair regions: `repair_p{page}_{i}` in `cluster_failed_boxes`. |
| Who stamps `pending_phase_5` | Contract defaults; explicit stamps in `visual/service.py`, `visual/worker.py`, `materialise_embedded.py`, `repair_methods.py`, `repair_pipeline.py`, `repair_reconcile.py`. Heuristic class in `noise.py`. Coverage reason in `embedded_coverage.py`. |
| Crop cleanup | In-memory `.close()` in repair/spot-check; staging via `cleanup_repair_staging` / `cleanup_all_repair_staging` (`repair_pipeline.py`); document staging via `cleanup_staging` (`result_store.py`) from `VisualOcrService.finalize_visual_summary`. |
| Cancellation | `CancellationToken.raise_if_cancelled` in `route_and_select_heavy_pages`; repair `_check_cancel`; worker-manager stdin cancel. |
| Page quantum | Fair scheduler admits **full OCR page** units only; quantum default 2. Repair runs **synchronously during selection**, not as separate scheduler units. |

### Route 1 — Full visual OCR / image-input / dense-form fallback

```text
ProcessingCoordinator._run_visual
  → VisualOcrService.route_and_select_heavy_pages
  → FairDocumentScheduler.admit_document (FULL_OCR_PAGE)
  → VisualOcrService.process_selected_pages
  → OcrWorkerManager.process_document
  → worker.process_document → process_page
       render_page → prepare_primary
       → adapter.recognise (combined detect+rec; optional limit_side / grayscale fallback)
       → analyse_page_profile / build_quality_evidence / compare_ocr_passes
       → noise.classify_raw_lines → _build_contract_lines
  → stamp PageResultState.FULL_VISUAL_OCR
```

Answers: detection not separate; combined pipeline; geometry after predict; no crops; IDs in `_build_contract_lines`; classify **cannot** run before recognition today; page-batch classify N/A until detect-first refactor; stamps in worker + service; crop cleanup N/A (page image close in `process_page`); cancel via worker manager; quantum after each completed page unit.

### Route 2 — Hybrid selection → full OCR

```text
route_and_select_heavy_pages
  → render probe (ocr_visibility_probe_dpi)
  → PageRouter.decide(..., recognise_crop=None)
  → FULL_VISUAL_OCR → selected[] → Route 1
```

Hybrid is **page routing**, not region OCR. Sparse embedded coverage (`evaluate_embedded_coverage`) can escalate to full OCR **without** Paddle during coverage.

### Route 3 — Embedded OCR verification (prod: no Paddle)

```text
PageRouter._decide_embedded
  → evaluate_embedded_coverage / evaluate_visual_agreement
  → materialise_verified_embedded_words → EMBEDDED_OCR_VERIFIED
```

Prod passes `recognise_crop=None`, so recognition spot-check is skipped. Handwriting classification is **not applicable** to native/embedded materialisation as a Paddle-bypass problem; markers are provisional defaults.

### Route 4 — Targeted repair + method fallback + repair→full OCR

```text
route EMBEDDED_OCR_TARGETED_REPAIR
  → VisualOcrService._ensure_repair_adapter
  → run_targeted_repair_pipeline
       cluster_failed_boxes → execute_regions
         repair_region_recognition_only → adapter.recognise_only
         repair_region_local_detection → adapter.detect_and_recognise_crop
       reconcile_repaired_page → publish EMBEDDED_OCR_TARGETED_REPAIR
       OR fallback_to_full_ocr → selected[] → Route 1
```

Geometry exists **before** crop recognition (native boxes). Classification can insert **after crop, before `recognise_crop` / `detect_recognise`**. Cleanup: `cleanup_repair_staging`. Cancel per region. **Not** fair-quantum sliced today.

### Route 5 — Batch OCR helper

`PaddleOcrAdapter.recognise_crops_batched` loops `recognise_only`. Repair currently iterates crops in `execute_regions` rather than always using this API.

### Route 6 — Glyph-quarantine salvage

`native/glyph_quarantine.apply_glyph_quarantine` inside native trust — **no Paddle**. Out of Phase 5 recognition-exclusion scope except where routing later selects visual OCR.

### Progress spine

Worker/repair/router emit → `VisualOcrService` callbacks → `ProcessingCoordinator.on_visual_progress` → `ProgressSnapshot` capped by `OVERALL_CAP`.

---

## 6. Inventory of every `pending_phase_5` location

### Classification categories (task taxonomy)

| Cat | Meaning |
|-----|---------|
| 1 | Real visual region that must be classified before local recognition |
| 2 | Page-level summary or diagnostic |
| 3 | Native/embedded item where HW classification is not applicable (or not the Paddle path) |
| 4 | Legacy provisional value to replace later |
| 5 | Test fixture or generated-contract reference |
| 6 | UI presentation value |
| 7 | Unclear — needs further investigation |

### Runtime stamps

| Location | What | Cat |
|----------|------|-----|
| `backend/app/contracts/ocr.py` `HandwritingAssessment` / field defaults on `PrintedOcrLine` / `PrintedOcrWord` | Lifecycle placeholder enum + defaults | 4 |
| `backend/app/contracts/ocr.py` `ProvisionalItemClass.HANDWRITING_CANDIDATE_PENDING_PHASE_5` | Heuristic noise class name | 4 |
| `backend/app/contracts/visual.py` `VisualPageResult.handwriting_assessment` + document `handwriting_assessment_pending` | Page/doc summary flags | 2 |
| `backend/app/extraction/visual/worker.py` `_build_contract_lines` / page result | Stamps every full-OCR line/word/page | **1** (must become real outcomes after classify) |
| `backend/app/extraction/visual/service.py` (8 stamp sites) | Route terminal page results (`FULL_VISUAL_OCR`, `VISUAL_NO_TEXT`, failures, retained paths) | 2 (page); underlying regions on full OCR are cat 1 when lines exist |
| `backend/app/extraction/visual/noise.py` | Heuristic `HANDWRITING_CANDIDATE_PENDING_PHASE_5` (low score + irregular aspect) — **not** a classifier | 4 (replace with real assessment; keep provisional class evolution careful) |
| `backend/app/extraction/routing/materialise_embedded.py` | Embedded verified words/lines default assessment | 3 |
| `backend/app/extraction/routing/repair_methods.py` | Repair candidates stamped pending | **1** (repair crops must classify before Paddle) |
| `backend/app/extraction/routing/repair_pipeline.py` | Published repair page assessment | 2 |
| `backend/app/extraction/routing/repair_reconcile.py` | Reconciled retained/repaired items | 1/3 mix (repaired visual → 1; retained embedded → 3) |
| `backend/app/extraction/routing/embedded_coverage.py` | Field/reason `handwriting_pending_phase_5` from ink-density heuristic | 2 (diagnostic reason, not region classify) |

### Tests / scripts / fixtures / generated / docs / UI

| Location | Cat |
|----------|-----|
| `backend/tests/test_correction5_ocr_quality.py` | 5 |
| `scripts/generate_targeted_repair_fixtures.py`, `scripts/accept_correction5_private_police.py` | 5 |
| `fixtures/synthetic/ocr/targeted-repair/MANIFEST.json`, `handwriting_pending.*` | 5 |
| `frontend/src/contracts/generated/{types,zod}.gen.ts`, `docs/contracts/openapi.json` | 5 |
| `frontend/src/features/visual/VisualInspectionPanel.test.tsx`, `PhaseStatusCard.tsx`, `visualApi.ts` comments | 6 |
| Phase 4/5 docs and ADRs mentioning pending | docs only |

**Do not blanket find-and-replace.** Category 1 sites need classification outcomes; category 3 should stay `not_applicable`; category 2 becomes aggregate of region outcomes; category 4/5 update with contracts.

Approximate production stamp density: ~8 in `service.py`, ~2 in `worker.py`, ~2–4 each in repair/materialise/coverage/noise, plus contract defaults.

---

## 7. Exact Phase 5 insertion points

Preferred order:

```text
authority decision → render/preprocess → local text detection
  → detector-owned region + geometry → deterministic classifier crop
  → writing-style classification → route
  → Paddle recognition only for printed → existing reconciliation
```

### Primary insertion (full-page OCR) — required later refactor

| Field | Value |
|-------|-------|
| File | `backend/app/extraction/visual/paddle_adapter.py` + `worker.py` |
| Functions | New detect-first API on `PaddleOcrAdapter`; `process_page` `_recognise` path |
| Current | Combined `recognise` → text+geometry |
| Phase 5 | Obtain detector boxes/polys first; build crops; classify; call recognition **only** for `printed` |
| Why here | Only place that guarantees handwritten/uncertain never reach recogniser on Route 1 |
| Risk | High — touches quality gate, dual-pass, dense-form, progress events (`paddle_ocr_pipeline`) |
| Test | Recognition-exclusion invariant across primary/fallback/grayscale passes |

### Repair insertion (already crop-shaped)

| Field | Value |
|-------|-------|
| File | `backend/app/extraction/routing/repair_methods.py` |
| Functions | `repair_region_recognition_only`, `repair_region_local_detection` |
| Current | Crop then immediate `recognise_crop` / `detect_recognise` |
| Phase 5 | Classify crop (and/or detected subcrops) before Paddle recognition |
| Why | Direct Paddle call sites with existing crops |
| Risk | Medium — repair quality/eligibility may change if HW regions abstain |
| Test | Repair handwritten/uncertain → no `recognise_only` / `detect_and_recognise_crop` |

### Service / worker result stamping

| Field | Value |
|-------|-------|
| Files | `visual/worker.py`, `visual/service.py`, `repair_reconcile.py`, `materialise_embedded.py` |
| Phase 5 | Write lifecycle + outcome evidence; stop blanket `PENDING_PHASE_5` on classified visual regions |
| Risk | Contract consumers / UI exhaustive enums |
| Test | Contract + Zod drift; UI exhaustive handling |

### New package

| Field | Value |
|-------|-------|
| Path | `backend/app/extraction/handwriting_router/` (replace README stub) |
| Responsibility | Preprocess crop → ONNX session → thresholds → public outcome; no geometry invention |
| Risk | Dependency boundary; session lifecycle vs OCR worker process |
| Test | Unit matrix §23 |

### Explicit non-insertion

- Do **not** classify whole pages when region crops exist.
- Do **not** run classifier on digital-native-only pages with no visual recognition path.
- Do **not** add page-level handwriting terminal routes.
- Do **not** call OpenAI / vision LLM.

---

## 8. Detection-recognition separation findings

**Finding:** Phase 4 production full OCR is a **combined** Paddle operation. There is no production detect-only call. Model bootstrap already loads separate det/rec model dirs (`scripts/bootstrap_ocr_models.py`, `PaddleOcrAdapter` ctor kwargs `text_detection_model_*` / `text_recognition_model_*`), but inference always uses pipeline `predict`.

**Minimal later refactor (Task 4; not this task):**

1. Retain existing Paddle detector models (`PP-OCRv5_mobile_det` default).
2. Add adapter method that returns detector geometry (+ detection scores) **without** publishing recognition text as authority — preferably true detect-only if PaddleOCR 3.x API allows; otherwise a tightly scoped interim that discards recognition text until classification permits recognition (must still prove no handwritten text enters printed transcript).
3. Create deterministic region crops from detector polygons (Pillow), page-local only.
4. Classify crops via handwriting router.
5. Invoke existing recogniser **only** for `printed` (crop recognition or constrained pipeline).
6. Preserve: preprocessing variants, detection confidence, region IDs, provisional reading order, selected-pass / quality-gate, repair logic, fair page scheduling.

**Do not:** add a second detector; change OCR model defaults; rewrite the whole Phase 4 pipeline; invent geometry; use OpenCV.

Repair path already separates “geometry exists” from “recognition call” more cleanly and is the easier first integration surface, but **release safety requires Route 1 exclusion**, so full-page split is mandatory for exit gates.

---

## 9. Contract proposal

### Current problem

`HandwritingAssessment` is a single value `pending_phase_5`, mixing lifecycle (“not assessed yet”), outcome, and Phase 6 readiness. `ProvisionalItemClass.handwriting_candidate_pending_phase_5` is a **heuristic noise label**, not a classifier outcome. Document flag `handwriting_assessment_pending: bool = True` is a coarse summary.

### Proposed separation (minimal)

**Classification lifecycle** (region/page applicable field):

```text
not_applicable | not_run | classified | unavailable | failed
```

**Classification / public routing outcome:**

```text
printed | handwritten | uncertain | non_text
```

Distinguish:

| Situation | Lifecycle | Outcome |
|-----------|-----------|---------|
| Classifier ran, abstained | `classified` | `uncertain` |
| Router disabled (Phase 4 compat) | `not_run` | omit or null outcome |
| Enabled but model missing / checksum / ORT down | `unavailable` | treat as operational `uncertain` for routing |
| Inference exception / NaN | `failed` | operational `uncertain` for routing |
| Embedded/native only | `not_applicable` | none |

**Minimum useful evidence fields (no secrets/paths/crops/text):**

- `outcome`, `lifecycle`
- `model_version`, `threshold_set_version`
- `decision_reason` (enum/code, not free-form document text)
- `inference_vs_safety_abstention` (bool or enum)
- existing `region_id` + detector-owned geometry (already on line/word)

**Do not expose:** local paths, crop images, document text, secret config, raw probability vectors (optional debug-only behind non-API diagnostics if ever needed).

### Consumers to update later (not this task)

- Backend: `contracts/ocr.py`, `contracts/visual.py`, all stamp sites in §6, health messages, tests
- Generated: `docs/contracts/openapi.json`, `frontend/src/contracts/generated/*`
- Frontend: visual inspection panel, any exhaustive switches on `HandwritingAssessment`
- Scripts/fixtures asserting `pending_phase_5`

Keep `pending_phase_5` temporarily as deprecated alias **or** migrate in one contract regen — prefer explicit lifecycle/outcome split over overloading the old enum.

---

## 10. Public outcomes versus model outputs recommendation

### Data evidence

No human-labelled ambiguous/uncertain crop set exists in-repo or under `fixtures/private/` for Phase 5. Synthetic `handwriting_pending.png` is a placeholder (`phase5_pending`), not a labelled train set. Obsolete `tmp/phase05/firm-gold-review` is **legal-fact** gold from the removed demand-letter product — out of scope and not HW crops.

### Recommendation: **Option A** (preferred)

ONNX model outputs probabilities for:

```text
printed | handwritten | non_text
```

Runtime derives public `uncertain` when:

- no class meets its threshold;
- top-two margin &lt; `minimum_class_margin`;
- competing threshold collisions;
- invalid / non-finite / wrong-shape output;
- model unavailable under enforced mode;
- input validation fails (empty/too-small crop, bad channels).

**Option B rejected** until consistently human-labelled ambiguous regions exist at scale.

| Topic | Decision |
|-------|----------|
| Model classes | 3-class |
| Public outcomes | 4-way including derived `uncertain` |
| Tie / collision | → `uncertain` |
| Invalid output | → `uncertain` + lifecycle `failed`/`unavailable` |
| Learned uncertain | **No** initially |
| Contract migration | Replace sole `pending_phase_5` with lifecycle + outcome |

---

## 11. Settings proposal

### Current reserved settings (`backend/app/settings/config.py`)

| Setting | Default | Used at runtime? | Env (`.env.example`) |
|---------|---------|------------------|----------------------|
| `printed_threshold` | 0.85 | **No** | `PRINTED_THRESHOLD` |
| `handwriting_threshold` | 0.70 | **No** | `HANDWRITING_THRESHOLD` |
| `uncertain_to_llm` | `True` | **No** | `UNCERTAIN_TO_LLM` |
| `handwriting_classifier_path` | `./models/handwriting_classifier/model.onnx` | **No** (health ignores) | `HANDWRITING_CLASSIFIER_PATH` |

No custom validators beyond `ge`/`le` on thresholds. No `handwriting_router_enabled` / `classifier_required` / `non_text_threshold` / `minimum_class_margin` today.

### Propose

| Action | Setting |
|--------|---------|
| **Add** | `handwriting_router_enabled: bool = False` — master switch; `False` preserves Phase 4 compat |
| **Add** | `handwriting_classifier_required: bool = False` — when enabled+required, broken model fails `/health/ready` |
| **Retain** | `printed_threshold`, `handwriting_threshold`, `handwriting_classifier_path` |
| **Add** | `non_text_threshold: float = 0.80` (calibrate on validation later) |
| **Add** | `minimum_class_margin: float = 0.10` |
| **Clarify / deprecate name** | `uncertain_to_llm` → keep reserved for Phase 6; rename docs to `uncertain_to_vision_reserved`; **do not enable OpenAI** in Phase 5 |
| **Add** | Optional `handwriting_classifier_batch_size: int` (bounded page-local batch) |

**Enforcement:** `handwriting_router_enabled=True` requires classification before local recognition on visual paths. Acceptance profile: enabled + required on CI/acceptance once model package ships; default local/dev may start enabled+optional.

**Validation:** thresholds in `[0,1]`; path must be relative/safe (never echo absolute path in API); if enabled+required, readiness verifies package.

---

## 12. Safe missing-model policy

Aligned with existing readiness doctrine: `HealthService.overall_state` fails readiness only when `required and status == FAIL` (`health/service.py`). `CheckState` is `pass` / `fail` / `not_configured` (no separate degraded check state; overall response may still use `degraded` literal in contract — currently aggregation is READY vs NOT_READY only).

| Mode | Behaviour |
|------|-----------|
| Router disabled | Phase 4 compatibility: combined Paddle path unchanged; lifecycle `not_run` |
| Enabled + ready | Classify before local recognition |
| Enabled + model missing / checksum mismatch / invalid manifest / labels / ORT missing / session init fail / smoke fail / NaN / bad shape / inference exception | **Do not** silently treat as printed; reserve affected visual regions as operational **`uncertain`**; **do not** call Paddle recognition for those regions; structured warnings; readiness reflects state |

| `classifier_required` | Enabled+broken effect on `/health/ready` |
|-----------------------|------------------------------------------|
| `false` (optional) | Ready overall; check `fail` or message degraded; processing still abstains to uncertain |
| `true` | Ready **fails** (`required` check `FAIL`) |

Disabled router → check remains `not_configured` / not required → ready.

Never leak absolute model paths in API messages.

---

## 13. Dependency and boundary proposal

### Current state

- `pyproject.toml`: no `onnxruntime`, `onnx`, `torch`, `torchvision`, `scikit-learn`, `openai`
- OCR optional group: `paddleocr`, `paddlepaddle`, …
- `scripts/check_dependency_boundary.py` forbids `onnxruntime` / `openai` / `cv2` / tesseract **everywhere**
- Inventory: Phase 5 ONNX noted as future, not added

### Narrowest structure (later tasks)

| Group | Packages |
|-------|----------|
| Production runtime | `onnxruntime` (CPU only) |
| Model-dev (non-runtime) | `onnx`, `torch`, `torchvision`, `scikit-learn` — **not** backend production imports |

Continue forbidding: `openai`, `cv2` app imports, TrOCR, Kraken, PyLaia, local VLM, unapproved HTR.

### Import allowlist for `onnxruntime`

- `backend/app/extraction/handwriting_router/`
- Narrow health verification in `backend/app/health/service.py` (or a helper imported only from health + router)
- Phase 5 verify/smoke scripts under `scripts/` (explicit prefixes)

Update later: `DEPENDENCY_INVENTORY.md`, `docs/dependencies/direct-dependencies.md`, `licence-inventory.md`, boundary script + tests, `pyproject.toml` / lockfiles, security review note.

---

## 14. Model package contract

Mirror Phase 4 bootstrap patterns (`scripts/bootstrap_ocr_models.py`, `.models/paddleocr/model-record.json` tree hashes + warm-up predict).

Proposed layout:

```text
models/handwriting_classifier/
├── README.md
├── model.onnx
├── labels.json
├── model-record.json
└── metrics.json
```

**`model-record.json` must define at least:**

model family/version/release status; training code version; ONNX opset; input tensor name/shape; dynamic vs fixed batch; colour mode; channel order; resize / aspect / padding / interpolation; normalisation mean/std; output tensor name; logits vs probabilities; class order; public-outcome mapping; threshold-set version; train/val/held-out manifest hashes; model SHA-256; provenance; pretrained-weight provenance; licence; creation timestamp; supported ORT version range; expected execution provider (`CPUExecutionProvider`).

**Verification failures (any → unavailable):** missing files; hash mismatch; wrong label order; wrong I/O shape; unsupported ops; session creation failure; synthetic inference failure; non-finite output.

Do not commit large binaries without explicit project policy; keep private training data gitignored.

---

## 15. Existing dataset and label inventory

| Area | Status (counts / structure only; no private contents) |
|------|--------------------------------------------------------|
| `fixtures/private/` | Gitignored (`fixtures/private/**` with allowlisted examples). Contains opaque PDFs (`private_*_001.pdf`), local named PDFs, manifests (`phase4-final-batch.local.json`, `phase45-routing.local.json`, …). **No** `phase5/` crop tree. |
| `fixtures/synthetic/ocr/handwriting_pending.{png,gold.json}` | Placeholder pending marker, not labelled HW classes |
| `fixtures/synthetic/ocr/targeted-repair/` | Includes handwriting-crop style fixture with `pending_phase_5` |
| `fixtures/extraction_acceptance/mixed_print_handwritten_like.*` | Acceptance placeholder, not train set |
| `models/handwriting_classifier/` | README only |
| Human HW crop labels (printed/HW/non-text/uncertain) | **None found** |
| Review tooling | No Phase 5 crop-label workflow in-repo; obsolete demand-letter gold under gitignored `tmp/` is irrelevant |

**Enough data to train / calibrate / held-out / learned uncertain?** **No** on all four.

**Proposed private location:** `fixtures/private/phase5/` (covered by existing `fixtures/private/**` gitignore). Optionally add `!fixtures/private/phase5/README.example.md` allowlist later.

---

## 16. Human-review status

No in-repository human reviewer records for writing-style crop labels. No approved Phase 5 labelling guide checked in. Synthetic fixtures are machine placeholders. Private PDFs exist for Phase 4 acceptance but are **documents**, not reviewed region-crop label sets.

**Conclusion:** Task 3 must create crop export + labelling workflow before any honest model training.

---

## 17. Dataset split and leakage-prevention policy

Splits: `train` / `validation` / `held_out`.

| Rule | Policy |
|------|--------|
| Grouping key | Original document id (opaque); all pages/crops from one document stay together |
| Near-duplicates | Duplicate/near-duplicate document groups stay in one split |
| Synthetic families | Template family stays in one split |
| Exact crop hash | Must not cross splits |
| Held-out | Untouched after threshold selection begins |
| Seed | Deterministic documented seed in split manifest |
| Manifests | JSON with group ids, counts, class support, hashes; store manifest SHA-256 in model-record |
| Leakage checks | Automated assert no shared doc id / crop hash across splits |
| Class support | Fail split if a split lacks minimum support for printed/HW/non_text (thresholds TBD after labelling) |
| Challenge slices | Digits, capitals, cursive, signatures, faint, fax, low-res, small, form fields, mixed, families |
| Mixed-label groups | Document if a document contains multiple classes — still keep group atomic; do not split by class across docs |

Do not create private dataset files in Task 1.

---

## 18. Threshold-selection policy

Select thresholds **on validation only**. Held-out forbidden for model/architecture/augmentation/calibration/threshold/margin tuning or repeated debugging.

**Safety-first objective order:**

1. Minimise handwriting-to-Paddle leakage (target **0** leaks).
2. Meet approved handwriting safe-bypass recall (threshold **not yet approved**).
3. Maintain acceptable printed-route precision.
4. Maximise printed retention recall without weakening 1–3.
5. Reduce unnecessary uncertainty only after safety gates.
6. Maintain usable non-text suppression.

**Deterministic routing behaviour:**

| Condition | Public outcome |
|-----------|----------------|
| No threshold passed | `uncertain` |
| Two+ thresholds passed / collision | `uncertain` |
| Low top-two margin | `uncertain` |
| Exact tie | `uncertain` |
| Invalid / non-finite / wrong shape | `uncertain` + failed lifecycle |
| Empty / too-small / too-large / bad channels | `uncertain` + validation reason |

Do not optimise overall accuracy alone.

---

## 19. Metrics and exit-gate definitions

### Primary safety metrics

| Metric | Definition | Release target |
|--------|------------|----------------|
| Handwriting safe-bypass recall | true HW routed as `handwritten` or `uncertain` / all true HW | **Approved corpus threshold required — none exists yet** |
| Handwriting-to-Paddle leak count | true HW sent to Paddle recognition | **0** |
| Uncertain-to-Paddle leak count | public `uncertain` sent to Paddle recognition | **0** |

Also define: HW→Paddle leak rate; HW predicted printed/non-text counts; printed-route precision; printed retention recall; printed→uncertain/HW; non-text suppression P/R; non-text→printed; abstention rate; per-class P/R/F1; support; confusion matrix; macro/weighted averages.

**Slices:** handwriting digits; hand-printed capitals; cursive; signatures; faint; fax/noisy; low-res; small crops; form fields; mixed print/HW; document families; public vs private project data.

### Exit-gate status

SoT §31 requires “Handwritten routing recall reaches the agreed corpus threshold” but **no numeric approval** exists in `docs/evaluation/` or ADRs.

**Phase 5 cannot be declared passed** until a threshold-approval ADR + evaluation document records the agreed recall (and any printed-precision floors). **Do not invent a percentage in this audit.**

---

## 20. Health/readiness proposal

Reuse `DependencyCheck` + `CheckState`; map classifier detail into `message` codes / internal enum without parallel health schema.

**Future classifier states (encode in check message or structured detail later):**

```text
disabled/not_configured
configured_ready
model_missing
manifest_invalid
checksum_invalid
runtime_unavailable
session_initialisation_failed
inference_smoke_failed
```

| Situation | `/health/ready` |
|-----------|-----------------|
| Classifier disabled | Pass (not_configured, required=false) |
| Enabled, optional, healthy | Pass |
| Enabled, optional, broken | Pass overall if only optional fail; processing abstains |
| Enabled, required, healthy | Pass |
| Enabled, required, missing/corrupt/checksum/smoke fail | **Fail ready** |

No absolute paths in responses. Replace stub `_future_checks()` entry for `handwriting_classifier` when Task 2 wires real verification. Leave `openai_vision` stub untouched (Phase 6).

---

## 21. Progress recommendation

| Item | Current |
|------|---------|
| Cap | `OVERALL_CAP = 65.0` in `progress_weights.py` |
| Contract | `MAX_PHASE4_PROGRESS_PERCENT = 65` in `documents.py` |
| Enforcement | Coordinator + session models clamp |
| Frontend | Assumes Phase 4 max 65 |

**Recommendation: keep overall progress cap at 65%.**

Classification time/counts fit inside existing visual page lifecycle via current operation events, region/page-local counts, elapsed classifier time, and classifier status — analogous to how repair emits `targeted_repair_*` without raising the cap.

Raising the cap requires a **separate ADR** and is out of Task 1. Only revisit if implementation proves classification cannot be represented honestly within the Phase 4 progress doctrine.

---

## 22. Fair-scheduling and performance considerations

| Concern | Proposal |
|---------|----------|
| WRR / aging / quantum | Classify **inside** the page work unit already admitted for full OCR; do not accumulate whole-document crops across quantum yields |
| Repair | Remains sync-in-selection today; classify per region before Paddle; honour `_check_cancel` |
| Batching | Page-level bounded classifier batches; reusable ORT session; **no** session-per-crop |
| Cancellation | Check before/after classifier batches |
| Cleanup | Release bitmaps/crops at page end (mirror repair `.close()`) |
| Hundreds of regions | Bound batch size; stream page regions; do not hold all crops for the document |
| Timing | Instrument classifier duration in page progress payloads |

Owners today: page quantum / yield — `FairDocumentScheduler.complete_work_unit`; deadlines — coordinator/settings; cancel — tokens + worker manager; crop cleanup — repair pipeline / worker image closes.

---

## 23. Test matrix

### Unit

Settings validation; manifest/checksum/labels; I/O tensor mismatch; preprocessing determinism; threshold matrix; margin abstention; ties; NaN/Inf; wrong shape; missing model; inference exception; safe abstention; reusable session; batched inference.

### Recognition exclusion (mandatory)

Automated proof for **every** local visual-recognition route:

```text
handwritten → no Paddle recognition call
uncertain → no Paddle recognition call
non_text → no Paddle recognition call
printed → Paddle recognition call allowed
```

Repository-wide invariant: fail if classification outcome is `handwritten` or `uncertain` **and** the same region id is passed to Paddle recognition.

### Integration

Full visual OCR; hybrid; targeted repair; repair fallback; embedded escalation; image input; missing classifier; cancellation; session cleanup; printed-only Phase 4 regression; route accounting / `final_route_histogram`; progress cap; monotonicity; fair scheduling.

### Dependency

Approved `onnxruntime` import passes; unapproved fails; OpenAI/OpenCV/HTR/training-lib imports from backend runtime fail.

### Contract/frontend

Deterministic OpenAPI; Zod drift; exhaustive enums; truthful UI for reserved HW/uncertainty (minimal).

---

## 24. Expected files to change in later tasks

| Task | Likely files |
|------|----------------|
| 2 | `contracts/ocr.py`, `contracts/visual.py`, `settings/config.py`, `.env.example`, `health/service.py`, `handwriting_router/*`, `scripts/check_dependency_boundary.py`, `pyproject.toml`, dependency docs, generated OpenAPI/Zod, tests |
| 3 | crop export scripts, `fixtures/private/phase5/` (gitignored data), labelling docs, train/export scripts under `scripts/`, `models/handwriting_classifier/*` (artifacts policy), model-dev dependency group |
| 4 | `paddle_adapter.py`, `worker.py`, `repair_methods.py`, `repair_pipeline.py`, `service.py`, noise/reconcile stamp sites, progress event types, exclusion tests |
| 5 | evaluation scripts/reports under `docs/evaluation/`, threshold ADR, held-out metrics JSON (no private images in git) |
| 6 | acceptance evidence, phase report, annotated tag (human-gated) |

---

## 25. Implementation sequence

```text
Task 2: contracts, settings, dependency boundary, model verifier,
        classifier runtime foundation and readiness

Task 3: crop export, human labelling workflow, grouped dataset splits,
        training pipeline and ONNX export

Task 4: runtime integration before Paddle recognition
        (detect-first full-page split + repair crop classify)

Task 5: validation threshold selection, untouched held-out evaluation,
        FP/FN analysis and performance

Task 6: release consolidation, clean acceptance run and annotated tag
```

Refinement vs handoff prompt: Task 4 must include the **detect/recognise split** as a first-class prerequisite, not a soft follow-up. Do not start Task 3 model training until labelling exists. Do not start Task 6 until recall threshold is human-approved.

---

## 26. Risks

| Risk | Mitigation |
|------|------------|
| Combined Paddle predict blocks safe bypass | Explicit detect-first refactor + exclusion tests on all routes |
| Silent printed fallback when model missing | Enabled+broken → uncertain; never printed |
| Heuristic `noise.py` HW candidates confuse metrics | Separate provisional class from classifier outcome |
| Fair quantum / repair sync asymmetry | Keep classify inside existing units; document repair not quantum-sliced |
| No labelled data → pressure to ship unvalidated model | Gate training on Task 3; refuse invented recall % |
| Contract enum break of frontend | Exhaustive handling + drift guard |
| ORT + Paddle coexistence on Windows memory | Page-local batches; single OCR worker; RSS instrumentation |
| Scope creep into Phase 6 OpenAI | Keep `uncertain_to_llm` reserved; boundary forbid `openai` |

---

## 27. Rollback strategy

- Feature flag `handwriting_router_enabled=False` restores Phase 4 combined path.
- Revert Task 4 integration commit(s) independently of contract expansions if needed.
- Do not delete Phase 4 tags; do not force-push.
- Model package can be removed without schema wipe if lifecycle supports `not_run`/`unavailable`.
- Keep exclusion tests red if rollback accidentally reintroduces HW→Paddle leaks while router enabled.

---

## 28. Open decisions requiring human approval

1. **Numeric handwriting safe-bypass recall threshold** (and any printed-precision floor) — ADR + evaluation sign-off.
2. **Acceptance profile defaults:** whether CI/acceptance sets `handwriting_classifier_required=true` once a model ships.
3. **Detect-only API strategy** if PaddleOCR 3.x cannot expose pure detection without recognition side effects — accept constrained interim vs block on upstream API.
4. **Whether to commit ONNX binaries** in-repo vs bootstrap-from-cache (like Paddle models under `.models/`).
5. **Labelling ownership / reviewer process** for private Phase 5 crops.

---

## 29. Explicit Phase 6/7 out-of-scope list

**Not in Phase 5:** OpenAI; vision LLM transcription; contact-sheet batching; `9065` regression; Phase 6 provider calls; dedicated local HTR; TrOCR; Kraken; PyLaia; Tesseract HTR; local VLM; Qwen; final reading order; final tables/forms; search; exports; workspace redesign; Redis; Celery; DB persistence; demand-letter functionality; Phase 4 UI follow-ups P2–P4 / Q1–Q3; OpenCV app imports; raising progress to 100%.

---

## 30. Baseline gate commands and results

Recorded on audit machine from HEAD `2e77590` / branch `phase-05-handwriting-routing` (documentation-only dirty files present). No code was modified to pass gates.

| Command | Result | Key output |
|---------|--------|------------|
| `uv lock --check` | **PASS** | Resolved 105 packages |
| `uv run python scripts/check_dependency_boundary.py` | **PASS** | Dependency boundary guard passed |
| `uv run python scripts/check_contracts.py` / `pnpm contracts:check` | **PASS** | Deterministic; hashes match committed contracts |
| `uv run python scripts/check_no_legacy_scope.py` | **PASS** | (run with private guard batch) |
| `uv run python scripts/check_no_private_corpus.py` | **PASS** | |
| `uv run ruff format --check backend scripts` | **PASS** | 278 files already formatted |
| `uv run ruff check backend scripts` | **PASS** | All checks passed |
| `uv run mypy backend scripts` | **PASS** | Success: 277 source files |
| `uv run pytest -q --tb=no` | **PASS** | 471 passed, 1 skipped in ~176s |
| `pnpm -C frontend format:check` | **PASS** | Prettier clean |
| `pnpm -C frontend lint` | **PASS** | 0 errors, 2 pre-existing warnings (`PdfCanvas.tsx`, `usePdfDocument.ts`) |
| `pnpm -C frontend typecheck` | **PASS** | `tsc -b` clean |
| `pnpm -C frontend test` | **PASS** | 24 files / 152 tests passed (~62s); canvas getContext warning only |
| `uv run --group ocr python scripts/verify_ocr_runtime.py` | **PASS** | `OCR runtime verification succeeded` (`PP-OCRv5_mobile_det` / `_rec`) |
| `uv run --group ocr pytest backend/tests/test_ocr_integration.py -v` | **SKIP** | Not re-run in this audit pass (optional `check_all` OCR integration step; unit + verify already green) |
| Full `pnpm check` (includes e2e, frontend build, WASM) | **SKIP (partial)** | Component gates above cover Phase 5-relevant baseline; e2e/build not re-run as one shot in Task 1 |
| Live OpenAI | **SKIP** | Forbidden for this task |
| Private transcript inspection | **SKIP** | Policy |

Any failure predating this task would be reported honestly; none of the executed component gates failed.

---

## 31. Task 1 conclusion

Phase 5 Task 1 is complete as an evidence-based design freeze:

- Git baseline valid for Phase 5 start.
- Insertion boundary identified: **detect → crop → classify → printed-only recognise**, with full-page combined predict as the main refactor risk and repair crops as the secondary call sites.
- Contracts must split lifecycle vs outcome; Option A model outputs; safe missing-model → operational uncertain.
- No labelled dataset and no approved recall threshold — training and “Phase 5 passed” are blocked on human process (Tasks 3 and 5 + open decisions).
- Progress stays at 65%. Exclusive page routes unchanged.
- No production code, contracts, dependencies, models, or private data were changed by this task.

**Stop after Task 1. Do not begin implementation.**
