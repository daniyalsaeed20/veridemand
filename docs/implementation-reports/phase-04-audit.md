# Phase 4 Independent Audit — Document Classification and Sequencing

**Audit date:** 2026-07-20  
**Auditor:** Fresh independent verification (not the Phase 4 implementer)  
**Method:** Authoritative doc/contract review + rules inventory + synthetic/adversarial classification probes + real gitignored reference-package process/classify (aliases only) + FR-CLS-06/authority API probes + instrumented no-reprocessing + sequence atomicity + lifecycle race suite + LLM zero-call proof + frontend code audit + contract dual-regen + full `check-all`

**Constraints honored:** No production code changes. No Phase 5 work. No Git tag create/move/delete. Audit probes and private aggregates lived only under gitignored `tmp/audit/`. Private filenames, extracted patient text, screenshots, and credentials were not committed.

---

## Final verdict

# FAIL

Commit `1556eccda10fe17cb8399d771ad7c1df7cda4afe` is **not** suitable for the immutable tag `phase-04-audited-pass`.

**Primary blockers:** On the real Amini/Jackman reference package, the existing Amini demand was classified as `police_report` at confidence **0.85** (not ambiguous), left **authoritative**, and therefore bypassed FR-CLS-06 authority defaults. Jackman demand DOCX defect fixtures were classified as `medical_record` / `bill_ledger` and likewise treated as authoritative evidence. The Phase 4 exit gate requires sample files to be correctly classified **or** surfaced for quick correction; high-confidence wrong types without ambiguity styling do not satisfy that bar for existing-demand safeguards.

Do **not** create `phase-04-audited-pass`. Do **not** begin Phase 5.

---

## Exact audited commit

| Field | Value |
|-------|-------|
| Branch | `phase-04-document-classification-sequence` |
| **Audited tip** | `1556eccda10fe17cb8399d771ad7c1df7cda4afe` |
| Tip subject | `Implement Phase 4 document classification and sequencing.` |
| Working tree at audit start | Clean |
| Working tree after probes | Clean of production changes; only this report + gitignored `tmp/audit/` |

### Baseline

| Field | Value |
|-------|-------|
| Requested tag | `phase-03-audited-pass` |
| Tag present in this clone | **No** (absent) |
| Baseline commit (accepted) | `4c6672e5e8064d697cb0cf229841a3f1f3b73e56` |
| Ancestor of audited tip | **Yes** |

### Prior tags (unchanged)

`phase-00-pass`, `phase-01-pass`, `phase-01-audited-pass`, `phase-02-audited-pass`  
(`phase-03-audited-pass` was never present here; no tags were created/moved/deleted during this audit.)

### Diff scope (`4c6672e..1556ecc`)

Two commits: Phase 3 hardening-audit documentation (`db89a3b`) + Phase 4 implementation (`1556ecc`). Diff contains classification services, optional LLM stub, process integration, session lock set, API PATCH/PUT sequence, contracts (`classification.ambiguous`, settings, error codes), frontend Documents workspace, synthetic fixtures/tests, readiness thresholds, and completion report. **No** Fact creation, chronology, billing interpretation, contradiction engine, live LLM provider, drafting, or export work.

Privacy: `docs/example/*.pdf|*.docx` remain gitignored and untracked. Classification rules contain **no** `Amini` / `Jackman` / case-specific identifiers.

---

## Scope result

| Check | Result |
|-------|--------|
| HEAD == audit target | PASS |
| Working tree clean before/after (production) | PASS |
| Descends from Phase 3 baseline commit | PASS |
| Prior phase tags unchanged | PASS (tag absence noted) |
| Diff limited to Phase 4 (+ Phase 3 audit docs) | PASS |
| No structured Facts created | PASS |
| No Phase 5+ scope in code | PASS |
| No private case docs committed | PASS |

---

## Requirement traceability

| FR | Code path | Contract | API | UI | Automated test | Manual / reference | Exit-gate evidence |
|----|-----------|----------|-----|----|----------------|--------------------|--------------------|
| **FR-CLS-01** | `features.py` → `rules.py` / `rules_config.py` → `decision.py` | `DocumentClassification`, Document classification fields | Via `POST .../process` | Proposed type + reason | `test_classification_rules.py`, `test_phase04_classification.py` | Real package (partial success) | Synthetic PASS; real package **gaps/blockers** |
| **FR-CLS-02** | `classify_with_llm_fallback` stub; gated by `enable_llm_classification` | `AppSettings.enable_llm_classification` | N/A (disabled) | N/A | Probe: 0 calls when off | N/A | PASS (optional/off per OD-12) |
| **FR-CLS-03** | Full enum + medical+imaging collapse | `enums.md` 11 values | Document.classification | Dropdown options | Unit taxonomy tests | Real package types exercised | PASS (taxonomy) |
| **FR-CLS-04** | **Absent** (no `extract_classification_metadata`, no Facts) | Fact entity deferred | None | None | None | None | See determination below |
| **FR-CLS-05** | `sequence.py`; `update_document_sequence` | `sequence_index`; `sequence_invalid` | `PUT .../documents/sequence`; PATCH sequence | Drag + keyboard reorder | `test_phase04_sequence.py`, probes | Reorder ~2 ms API | PASS (plumbing) |
| **FR-CLS-06** | `authority.py` defaults + PATCH guard | `treat_as_secondary_evidence`, exclude | PATCH document | Warning + secondary toggle | `test_classification_authority.py`, demand DOCX synthetic | **Real demand misclassified** | **FAIL on real package** |

Deferred only where Module 04 §10 / OD-06 / OD-12 explicitly permit (FR-CLS-04 Facts; LLM live; provisional threshold). FR-CLS-06 is **not** deferrable.

---

## FR-CLS-04 determination

| Layer | Finding |
|-------|---------|
| Prototype FR-CLS-04 | “Extract provider, insurer, claimant, and date-range metadata where applicable.” |
| Module §5.1 | Metadata are suggested **`Fact`** instances with spans — not Document fields. |
| Module §10 | Explicitly: “FR-CLS-04 metadata `Fact` extraction is deferred to Phase 5; classification uses spans for rule features only.” |
| `open-decisions.md` | **No OD** authorizing FR-CLS-04 deferral (only OD-06 thresholds, OD-12 LLM). |
| Implementation | No Fact creation; no document-level provider/insurer/claimant/date-range labels; spans used only as rule features. |

**Distinctions applied**

1. **Document metadata for classification/display** — not present beyond type/confidence/reason.  
2. **Suggested case Facts (Phase 5)** — correctly absent; Module §10 authorizes.  
3. **User-visible extracted exact values** — absent (acceptable if Facts deferred).  
4. **Internal classification features** — present (filename tokens, early usable spans).

**Ruling:** Deferral of **Fact-shaped** FR-CLS-04 outputs is authorized by Module 04 §10 (canonical module design), even though no numbered OD exists. Completing absence of even lightweight non-Fact display metadata is a **nonblocking documentation/process gap** (prototype wording still lists metadata; completion report over-claims “strict Phase 4 scope” without an OD). **Not** treated as the primary blocking defect for this audit — the reference-package FR-CLS-06 failures are.

---

## Taxonomy and rules inventory

### Taxonomy

Canonical 11-value `DocumentClassification` in contracts and `app.models.enums` (matches frontend options):  
`police_report`, `insurer_correspondence`, `medical_record`, `imaging_report`, `bill_ledger`, `lien`, `wage_loss`, `photographs`, `existing_demand`, `template`, `other`.  
No implementation-only categories. Existing demand and template are distinct. Medical+imaging collapse keeps embedded imaging as `medical_record`. Bill+ICD stays ledger when billing dominates. Weak single keyword → `other` / ambiguous.

### Rules inventory (`rules_config.py` / `rules.py` / `features.py` / `decision.py`)

| Mechanism | Present | Notes |
|-----------|---------|-------|
| Filename rules | Yes | Weights 0.30–0.45; filename sum capped at 0.45 |
| Heading rules | Yes | Content rules re-matched on headings at 0.9× weight |
| Key-phrase content rules | Yes | Domain phrases 0.80–0.90 |
| Structural/layout | Limited | Image-like file type → photographs |
| Page-count | Captured in features | Not a primary scorer |
| Native/OCR usable policy | Yes | Suppresses `insufficient_coverage`, failed OCR, etc. |
| Table/billing indicators | Phrase-based | CPT / ledger / ICD phrases |
| Demand/template indicators | Yes | Strong demand/template phrases |
| Category weights / negative | Additive weights; pops imaging when medical present; pops medical when bill dominates + ICD | |
| Precedence / tie-break | `precedence.py` + `PRECEDENCE_TIERS` | Score → tier → enum value |
| Confidence | Top score, caps | Filename-only ≤0.45; no usable text ≤0.40 |
| Ambiguity | Gap `< 0.12`; filename vs content disagreement | |
| Determinism | Yes | Unit `test_deterministic_same_input` |

**Hidden / provisional thresholds:** `rule_confidence_threshold=0.55`, `AMBIGUITY_SCORE_GAP=0.12`, `FILENAME_ONLY_CAP=0.45`, multi-phrase weight stacking (easily saturates at 1.0). Documented provisionally in `docs/readiness/04-classification-thresholds.md` (OD-06).

**Case identifiers in rules:** None found (`Amini`/`Jackman` absent from classification package).

---

## Confidence and ambiguity findings

- Raw category score = sum of matched rule weights (content uncapped until total min(1.0); filename capped 0.45).  
- Confidence ≈ winning score after caps; **not** calibrated probability.  
- `0.55` is a provisional cutoff (OD-06); scores are not length-normalized across documents.  
- Close top/second scores set `ambiguous=True` and Amber `classification.ambiguous` Issue.  
- Single strong phrase can yield confidence 1.0 (content + heading double-count).  
- Filename-only below threshold forces `needs_correction`.  
- Rationale lists matched rule phrases (safe labels), not private excerpts.  
- UI shows “Confidence: N%” without explicitly labeling “classification confidence / not legal certainty” (minor wording gap).  
- **UI ambiguity styling only when confidence < 0.55** — high-confidence ambiguous/wrong rows (e.g. demand→police at 0.85) are **not** highlighted.

Threshold sweep at 0.54 / 0.55 / 0.56 on strong police text: all confident `police_report`. Filename-only `police.pdf` with unrelated text: confidence 0.35, needs correction.

---

## Synthetic fixture analysis

Committed builders in `backend/tests/fixtures/upload_builders.py` are synthetic, PII-free, phrase-aligned with illustrative gold — **not** copies of private PDFs. Unit/integration suites exercise positive taxonomy cases, misleading filenames, medical+imaging, demand keyword stuffing, weak keywords, and demand non-authority.

**Material differences vs real package**

| Aspect | Synthetic | Real package |
|--------|-----------|--------------|
| Text density | Dense category phrases on page 1 | Narrative demands cite police/medical/ICD in early pages |
| Filenames | Category-obvious (`police.pdf`) | Safe aliases only in probes; real stems are private |
| Billing | Explicit “Billing Ledger CPT…” | Landscape eCW ledger → **filename-only** 0.45 in this run |
| Demands | Explicit “Demand for Settlement…” | Demand body discusses evidence → **mis-typed as police/medical/bill** |

Synthetic-only evidence is **insufficient** for the reference-package exit gate (confirmed by real run).

---

## Real reference-package classifications

**Package location:** gitignored `docs/example/` (present; completion report incorrectly claimed absent).  
**Probe:** `tmp/audit/phase04_audit_probes.py` → `tmp/audit/phase04_probe_results.json` (gitignored).  
**Wall time:** ~32–46 s full process+classify (native-heavy; classification itself sub-second after extraction).

Safe aggregates only:

| Alias | Proposed | Conf | Runner / notes | Authority | Ambiguous UI? | Correction needed |
|-------|----------|------|----------------|-----------|---------------|-------------------|
| `police` | `police_report` | 1.00 | OK | Authoritative | No | No |
| `insurer` | `insurer_correspondence` | 1.00 | OK | Authoritative | No | No |
| `ecw_medical` | `medical_record` | 1.00 | OK | Authoritative | No | No |
| `ecw_billing` | `bill_ledger` | 0.45 | Filename-only | Authoritative | Yes (<0.55) | Confirm/correct quickly |
| `long_medical` | `medical_record` | 1.00 | OK | Authoritative | No | No |
| `existing_demand` | **`police_report`** | **0.85** | Reason: content “police report” | **Authoritative (exclude=false)** | **No** | **Yes — blocking** |
| `template` | `template` | 0.40 | Filename | Non-authoritative / excluded | Yes | Optional confirm |
| `jackman_demand_1` | **`bill_ledger`** | 0.85 | ICD-10 phrase | **Authoritative** | No | **Yes — blocking** |
| `jackman_demand_2` | **`medical_record`** | 0.85 | Physical examination | **Authoritative** | No | **Yes — blocking** |
| `jackman_demand_3` | **`medical_record`** | 0.85 | Physical examination | **Authoritative** | No | **Yes — blocking** |

`existing_demand_authority` list after classify was **empty** (no document remained `existing_demand`).

Correction/reorder API on package: PATCH ~2 ms, PUT sequence ~2 ms; **0** native/OCR reruns under instrumentation.

Classification did not itself re-run OCR for corrections; initial package processing used extraction as expected.

---

## Existing-demand authority (FR-CLS-06)

| Behavior | Synthetic demand DOCX | Real Amini demand |
|----------|----------------------|-------------------|
| Classifies as `existing_demand` | PASS | **FAIL** → `police_report` |
| Default non-authoritative / excluded | PASS | **FAIL** (authority defaults never applied) |
| Secondary enable API (existing_demand only) | PASS | N/A (wrong type) |
| Template secondary rejected | PASS (400 `document_invalid_patch`) | Template OK excluded |
| Flip-flop reclassify restores defaults | PASS | — |
| Secondary toggle alone ≠ primary | PASS while exclude remains true | — |
| `is_authoritative_evidence` with secondary+unexcluded | Returns True; contracts still expose `treat_as_secondary_evidence` for Phase 5 | Nonblocking naming conflation |

**Blocking:** Real existing demand became authoritative `police_report` evidence. FR-CLS-06 guard is classification-gated; misclassification nullifies it.

---

## Secondary-evidence result

- Only `existing_demand` may enable secondary; other types rejected (`document_invalid_patch`).  
- Templates cannot enable secondary.  
- Authority independent of sequence order.  
- Exclude overrides helper authority while `exclude_from_drafting=true`.  
- Automatic reclassify reapplies defaults for demand/template types.  
- Contracts expose `classification` + `treat_as_secondary_evidence` + `exclude_from_drafting` for Phase 5 distinction.  
- No Phase 5 behavior implemented (correct).

---

## Correction / locking result

| Check | Result |
|-------|--------|
| Correct / confirm category | PASS |
| `classification_locked` blocks auto reclassify | PASS (`classification_locked`) |
| Locked survives re-process | PASS |
| Revert unlocks + rules-only reclassify | PASS |
| Invalid category | 422 |
| Cross-session document PATCH | 404 |
| Deleted document PATCH | 404 |
| Dual manual PATCH last-wins | PASS |
| Correction does not alter tokens/spans | PASS (span/page counts stable) |

Concurrent `before_classification_commit` DELETE races: existing suite PASS (7 tests including 10× stress).

---

## No-reprocessing evidence

Instrumented after initial process: PATCH classification, confirm, exclude, sequence, locked classify attempt.

| Counter | After presentation ops |
|---------|------------------------|
| Native extract | 0 |
| OCR page | 0 |
| Thumbnails | 0 |

Reference-package correction/reorder likewise **0** native/OCR hits. No LibreOffice/OCR init observed on classification-only paths.

---

## Sequence result

- `SEQUENCE_RANK`: police → insurer → medical → imaging → bill → lien → wage → photos → other → existing_demand → template; upload-order then `document_id` tie-break.  
- Contiguous indices assigned on classify.  
- Deterministic unit tests PASS.  
- Provisional policy (not doctrine chronology) — acceptable with documentation.

### PUT `/documents/sequence` atomicity

| Case | Status | Prior order preserved | HTTP 500 |
|------|--------|----------------------|----------|
| Valid full reorder | 200 | N/A | No |
| Duplicate IDs | 400 `sequence_invalid` | Yes | No |
| Unknown / missing / extra / cross-session | 400 `sequence_invalid` | Yes | No |
| Empty list | 422 | Yes | No |
| After session delete | 404 | N/A | No |

Validation before mutation confirmed. Error envelope field is `error_code` (not nested `error.code`).

---

## Lifecycle race result

- `test_classification_delete_races.py`: DELETE during `before_classification_commit` → no late commit, no HTTP 500 (10×).  
- Generation / `deleting` barriers in `ClassificationService._classify_document_locked` before commit.  
- Events emitted only after successful `_apply_decision`.  
- Phase 3 `_expire_locked` limitation not worsened by Phase 4 classification path (no production lifecycle rewrite).  
- Zero recreated session/document state observed in race suite.

---

## Optional LLM result

| Check | Result |
|-------|--------|
| Default `enable_llm_classification` | `false` |
| Standard process provider calls | **0** |
| Stub when enabled + needs_correction | Invoked; returns `None` (no fabrication) |
| Request shape forbids full PDF | Compact snippet ≤500 chars |
| Categories validated by enum | Yes |
| Usable without LLM | Yes |

---

## Frontend / manual acceptance

Documents workspace (`DocumentList.tsx` / `documentClassification.ts`):

- Proposed category, confidence, rationale, confirm, correction dropdown, exclude, secondary toggle, existing-demand / template warnings, drag-and-drop + keyboard reorder, save note, viewable when classified.  
- Failed reorder does not mutate local order (API-first).  
- Backend Zod/client validation present for Document fields.  
- Locked state inferred from `user-confirmed` reason prefix (no dedicated wire flag — acceptable given session lock set).  
- Ambiguous styling **only** for confidence < 0.55 — does not consume Issue `classification.ambiguous` or high-confidence conflicts.  
- Confidence not labeled as non-legal (minor).  
- Existing demand warning only if `classification === existing_demand` — **misses misclassified real demand**.

**Manual timing (auditor API + code review; single nontechnical tester not measured):**

| Action | Time |
|--------|------|
| Classification correction API | ~2 ms |
| Sequence update API | ~2 ms |
| Package process+classify wall | ~32–46 s (extraction-dominated) |

Exit-gate “correction within seconds” is met for API/plumbing; **usability of discovering wrong high-confidence types is not**. Limitation: single-auditor measurement only.

---

## Performance result

| Metric | Observation |
|--------|-------------|
| Rule classify (synthetic text) | Sub-millisecond |
| Full reference package process+classify | ~32–46 s |
| Explicit reclassify / PATCH | Milliseconds; no OCR init |
| Sequence update | ~2 ms |
| Unexpected OCR/LibreOffice on PATCH | None observed |

Classification is lightweight relative to Phase 2/3 processing.

---

## Contract result

| Item | Result |
|------|--------|
| `classification.ambiguous` Issue type | Canonical; used on ambiguous/low-confidence decisions |
| `classification_locked`, `document_invalid_patch`, `sequence_invalid` | In error catalogue + DomainError map |
| Authority fields | `treat_as_secondary_evidence`, `exclude_from_drafting` (contracts win over module `AuthorityMode` prose) |
| Pydantic ↔ JSON Schema ↔ Zod | `check-all` dual-regen + drift OK |
| Implementation-only enums | None found |
| Ambiguous as Issue vs Document state | Issue type is canonical; Document has no `ambiguous` bool — UI under-uses Issues |

`classification.ambiguous` as Amber Issue is appropriate at this stage; conceptual duplication with confidence-only UI highlighting is a gap, not a contract error.

---

## Clean verification

| Gate | Result |
|------|--------|
| Backend ruff format / check | PASS |
| Backend mypy | PASS |
| Backend pytest | **198 passed** |
| Frontend format / lint / typecheck | PASS |
| Frontend tests | **9 passed** |
| Frontend production build | PASS |
| Contract generate ×2 + drift | PASS |
| `node scripts/check-all.mjs` | PASS |
| Repo-safety (private binaries untracked) | PASS |
| Reference-package classify | Executed (see blockers) |
| No-reprocess probes | PASS |
| Lifecycle race probes | PASS |

No test-count reduction vs completion claim.

---

## Adversarial classification summary

| Case | Outcome |
|------|---------|
| `medical_bill.pdf` + narrative | `medical_record` (correct) |
| `medical_records.pdf` + ledger | `bill_ledger` (correct) |
| Generic / blank | `other` ambiguous |
| Demand + all taxonomy keywords | `existing_demand` (ambiguous) |
| Medical + embedded imaging | `medical_record` |
| Insurer + treatment summary | `insurer_correspondence` ambiguous (tied medical) |
| Bill + diagnoses | `bill_ledger` |
| Photo image type | `photographs` needs correction |
| Template placeholders | `template` |
| Lien mentioning insurer | **insurer** ambiguous (correctable) |
| Wage on medical letterhead | **medical** ambiguous (correctable) |
| Weak keyword / near-tie | Ambiguous / other |

Synthetic adversarial behavior is mostly safe (ambiguity surfaced). Real narrative demands are the failure mode.

---

## Events and privacy

`document.classified` fields: ids, status (category), message (rule rationale), progress/error null.  
No private filenames, patient text, claim numbers, or paths in event messages (probe). Messages are rule rationales. Events only after successful commit.

---

## Blocking defects

1. **B-01 — Real existing demand misclassified as authoritative `police_report`.** Confidence 0.85; not ambiguous; FR-CLS-06 defaults skipped; UI warning absent. Violates required reference-package behavior and exit-gate “correct or quickly surfaced.”  
2. **B-02 — Jackman demand defect fixtures classified as authoritative medical/billing evidence.** Treated as evidence packages rather than demand/template-style non-evidence.  
3. **B-03 — High-confidence wrong types are not surfaced for review.** Ambiguity UI and Issues do not catch saturated single-category wins when narrative demands cite evidence keywords.

## Nonblocking gaps

1. FR-CLS-04 Fact metadata deferred (Module §10) without a numbered OD; no lightweight document metadata labels either.  
2. LLM live path stub-only (OD-12) — acceptable.  
3. Provisional 0.55 threshold / multi-phrase score inflation (OD-06).  
4. Sequence policy provisional.  
5. `phase-03-audited-pass` tag missing in clone (baseline commit OK).  
6. Frontend confidence wording / ambiguous Issue underuse.  
7. `is_authoritative_evidence` naming conflates secondary-enabled demand with “authoritative” when un-excluded (contracts still distinguishable).  
8. Nontechnical multi-user UI timing not measured.  
9. Completion report claimed reference package absent — incorrect for this workspace.  
10. Adversarial lien/wage ties prefer competing categories (flagged ambiguous — acceptable).

---

## Comparison to completion report

Completion self-assessed **PASS WITH GAPS** without a real package run. This audit executed the package and found **blocking** FR-CLS-06 / exit-gate failures. Synthetic and plumbing claims largely hold; reference-package and demand-authority claims do not.

---

## Final verdict (restated)

# FAIL

Commit `1556eccda10fe17cb8399d771ad7c1df7cda4afe` is **not** suitable for the immutable tag `phase-04-audited-pass`.

Stop. Do not begin Phase 5. Do not create, move, or delete any Git tag.
