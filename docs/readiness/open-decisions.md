# Open Decisions (Pre-Implementation Readiness)

**Status date:** 2026-07-19  
**Scope:** Genuine ambiguities and unresolved implementation choices found under `docs/`.  
**Rule:** Do not invent product requirements. Recommendations below are readiness guidance only; they do not amend doctrine in `docs/prototype_documentation.md`.

---

## OD-01 — OCR / native routing thresholds remain provisional

| Field | Content |
|-------|---------|
| **Affected** | Module 03; [`03-ocr-thresholds.md`](../modules/03-ocr-thresholds.md) (`thresholds_version` `0.1-provisional`); `AppSettings` OCR/native knobs; FR-EXT-02..07 |
| **Why it matters** | Routing wrong pages to native vs OCR drives silent failures vs demo latency. Defaults exist but baselines are `todo_measure`. |
| **Options** | (A) Ship Phase 3 with provisional defaults and calibrate after hardware runs. (B) Block Phase 3 until firm corpus measurement. (C) Hard-code corpus-specific thresholds into the product. |
| **Recommended** | **A** — implement with provisional defaults; record measured baselines from readiness OCR spike / Phase 3 bench; keep illustrative-only label for `docs/example/`. |
| **Consequences / risks** | Early demos may over-OCR (slow) or under-OCR (weak native). Fail-open-to-OCR reduces silent wrong native text. |
| **Blocks a phase?** | **No** for Phase 0–2. **Soft-blocks honest Phase 3 exit** until `todo_measure` rows are filled with real timings. |
| **Resolve by** | Phase 3 (calibration); revisit before Phase 10 claims. |

---

## OD-02 — Contract sync: hand-maintained Zod vs generated frontend schemas

| Field | Content |
|-------|---------|
| **Affected** | Module 00; [`docs/contracts/README.md`](../contracts/README.md) (“hand-maintained Zod until CI generation”); Module 00 §5.1 / §10 |
| **Why it matters** | Duplicate field shapes drift and break Phase 0 exit (health payload parity). |
| **Options** | (A) Hand-maintain Zod mirrors indefinitely. (B) Pydantic as machine SoT → JSON Schema → generated Zod + CI drift check. (C) OpenAPI-only frontend types without Zod. |
| **Recommended** | **B** — see [`contract-generation.md`](./contract-generation.md). Treat contracts Markdown as human design SoT; Pydantic as runtime machine SoT. |
| **Consequences / risks** | Generator tool choice still needs confirmation (non-blocking if Phase 0 picks one chain). Temporary bootstrap may copy schemas once, then generate. |
| **Blocks a phase?** | **No** for starting Phase 0. **Yes** for claiming Phase 0 complete without a parity mechanism. |
| **Resolve by** | Phase 0 (select generator + CI check). |
| **Status (2026-07-19)** | **Resolved in Phase 0** — chose option **B** with `json-schema-to-zod@2.6.1`; artifacts under `contracts/generated/` and `frontend/src/schemas/generated/`; drift gate via `scripts/check-contracts.mjs` + `scripts/proof-drift-fails.mjs`. |

---

## OD-03 — Health endpoint `app_version` source

| Field | Content |
|-------|---------|
| **Affected** | [`health-response.md`](../contracts/entities/health-response.md); Module 00 §10 |
| **Why it matters** | Optional field; demo/support needs a stable way to know which build was exercised. |
| **Options** | (A) Omit until first tagged release. (B) Package metadata / `pyproject` version. (C) `git describe` at build time. |
| **Recommended** | **B** with literal `0.0.0-dev` until packaging exists; document in health example. |
| **Consequences / risks** | Low; field is optional. |
| **Blocks a phase?** | No. |
| **Resolve by** | Phase 0. |
| **Status (2026-07-19)** | **Resolved in Phase 0** — option **B**: `APP_VERSION` / package metadata default **`0.0.0-dev`** exposed on `HealthResponse.app_version`. |

---

## OD-04 — Session TTL / cleanup scheduler mechanism

| Field | Content |
|-------|---------|
| **Affected** | Module 01 §10; FR-SES-04 |
| **Why it matters** | Expired sessions must clean temp files even after failed jobs; mechanism must be test-callable. |
| **Options** | (A) Background `asyncio` task. (B) Lazy cleanup on next API call. (C) APScheduler / threading timer. |
| **Recommended** | **A** for runtime + explicit cleanup callable from tests/`finally` (Module 01 already requires test-callable cleanup). |
| **Consequences / risks** | Lazy-only cleanup can leave disk until next request. |
| **Blocks a phase?** | No for Phase 0. Must resolve for Phase 1 exit. |
| **Resolve by** | Phase 1. |

---

## OD-05 — DOCX → PDF viewing converter on Windows

| Field | Content |
|-------|---------|
| **Affected** | Module 02 §10; FR-UPL-06 |
| **Why it matters** | Viewer needs a canonical PDF copy of DOCX uploads; Windows converter choice affects install burden. |
| **Options** | (A) LibreOffice headless. (B) Microsoft Word COM automation. (C) Defer view-copy and show DOCX-derived text only until LibreOffice is available. |
| **Recommended** | **A** when available; document missing converter as a **non-blocking** Phase 1 limitation with explicit error (`upload` error code), not silent skip. |
| **Consequences / risks** | Without converter, DOCX highlight/viewer path is incomplete for those files. |
| **Blocks a phase?** | Soft-blocks full FR-UPL-06 demo; does not block Phase 0. |
| **Resolve by** | Phase 1–2. |

---

## OD-06 — Classification rule confidence thresholds

| Field | Content |
|-------|---------|
| **Affected** | Module 04 §10; FR-CLS-01..02 |
| **Why it matters** | When to call optional LLM fallback vs keep rule label. |
| **Options** | (A) Provisional numeric threshold + measure on corpus. (B) Rules-only until Phase 4 measurement. (C) Always LLM. |
| **Recommended** | **B** for MVP (LLM optional/off); add provisional threshold in Phase 4 without inventing corpus SLA. |
| **Consequences / risks** | More manual corrections early; aligns with “LLM not primary.” |
| **Blocks a phase?** | No for Phase 0–3. |
| **Resolve by** | Phase 4. |

---

## OD-07 — Firm-approved gold location and approval status

| Field | Content |
|-------|---------|
| **Affected** | Module 12 §10; [`docs/example/gold/`](../example/gold/); Phase 5–7, 10 exit gates |
| **Why it matters** | Illustrative gold is explicitly not lawyer-final truth. Exit gates that “match the gold set” are dishonest without firm approval. |
| **Options** | (A) Keep illustrative gold for harness shape only; store firm gold outside public tree. (B) Promote illustrative to firm_approved without lawyer review (forbidden). (C) Skip gold-based exit gates. |
| **Recommended** | **A** — copy `GOLD_CASE_TEMPLATE.md` to a controlled firm path; set `firm_approved` only after lawyer/paralegal sign-off. |
| **Consequences / risks** | Phases 5–7/10 can demo against illustrative keys but cannot claim honest gate pass until approved. |
| **Blocks a phase?** | **Does not block Phase 0–4.** **Blocks honest Phase 5, 6, 7, 10 exit claims.** |
| **Resolve by** | Before claiming Phase 5 exit; required again for Phase 10. |

---

## OD-08 — Attorney waiver policy (who may waive Red blockers)

| Field | Content |
|-------|---------|
| **Affected** | Module 08 §10; FR-REV-*; export blockers |
| **Why it matters** | Who can waive Red/blocking issues changes ethics/risk posture. |
| **Options** | (A) Any session user (paralegal) with required reason. (B) Attorney-only role flag. (C) No waivers in prototype (must resolve). |
| **Recommended** | **A** for single-user prototype with mandatory reason + decision log; document that hosted pilot needs roles. |
| **Consequences / risks** | Over-waiver risk in demo; mitigated by decision log and `allow_final_export_with_red_issues=false` default. |
| **Blocks a phase?** | No for Phase 0–6. Resolve before Phase 7–9 demo claims. |
| **Resolve by** | Phase 7. |

---

## OD-09 — Draft narrative assembly: template vs LLM vs both

| Field | Content |
|-------|---------|
| **Affected** | Module 09 §10; FR-DRF-01..06; Phase 8 |
| **Why it matters** | Affects LLM dependency, cost, and support-ID enforcement for first complete demand. |
| **Options** | (A) Deterministic / template assembly first. (B) LLM draft from approved package only. (C) Hybrid (template skeleton + LLM paragraphs). |
| **Recommended** | **A** for first Phase 8 exit (docxtpl loop); add **B/C** only after support-ID contract is proven. |
| **Consequences / risks** | Template-only prose is less “letter-like” early; safer for unsupported-statement rate. |
| **Blocks a phase?** | No before Phase 8. |
| **Resolve by** | Phase 8. |

---

## OD-10 — Final attorney confirmation signal before final export

| Field | Content |
|-------|---------|
| **Affected** | Module 10 §10; FR-VAL-03; `ExportKind` final |
| **Why it matters** | Spec requires attorney confirmation for final export; UI/policy not specified. |
| **Options** | (A) Explicit boolean `attorney_confirmed` on export request. (B) Session status transition. (C) Rely only on preflight gate. |
| **Recommended** | **A** — explicit confirmation payload + decision log entry. |
| **Consequences / risks** | Without it, final export may violate product doctrine. |
| **Blocks a phase?** | No before Phase 9. |
| **Resolve by** | Phase 9. |

---

## OD-11 — Module-local packaging types vs contracted entities

| Field | Content |
|-------|---------|
| **Affected** | Modules 06/09 (`ProviderTreatmentSummary`, `BillingLedger`, `DemandDraft`, …); contracts pack |
| **Why it matters** | Ambiguity whether these need API schemas or stay session-internal. |
| **Options** | (A) Keep session-internal until a UI needs them; expose only contracted entities. (B) Add full contracts now. (C) Fork field shapes in modules. |
| **Recommended** | **A** — do not redefine shapes in modules; promote to `docs/contracts/` only when an API/UI requires them. |
| **Consequences / risks** | Temporary ad-hoc JSON in services; mitigated by contracts-win rule. |
| **Blocks a phase?** | No. |
| **Resolve by** | As needed Phase 6 / 8 (when API surfaces them). |

---

## OD-12 — Optional LLM provider / consent controls

| Field | Content |
|-------|---------|
| **Affected** | Module 11 §10; FR-AI-*; classification fallback |
| **Why it matters** | Provider choice and consent are deferred; extraction MVP must not depend on them. |
| **Options** | (A) Keep disabled until post–extraction-MVP. (B) Select provider in Phase 4 for classification only. (C) Enable semantic extraction early. |
| **Recommended** | **A**; optionally **B** for classification only after rules path works. Never **C** before Phase 5 exit. |
| **Consequences / risks** | Classification ambiguity queues more manual work. |
| **Blocks a phase?** | No. |
| **Resolve by** | When enabling Module 11 / optional CLS LLM (after Phase 5). |

---

## OD-13 — Severity / blocker policies need attorney-approved configuration

| Field | Content |
|-------|---------|
| **Affected** | Module 07 §10; `Issue.blocking`; issue-types taxonomy |
| **Why it matters** | Taxonomy alone does not decide legal severity; firm may want different blockers. |
| **Options** | (A) Ship defaults from issue-types + gold expected severities; allow session config later. (B) Block Phase 7 until firm config. |
| **Recommended** | **A** with documented defaults; firm overrides before Phase 10 claims. |
| **Consequences / risks** | Demo blockers may not match firm preference. |
| **Blocks a phase?** | Soft-blocks honest Phase 10; not Phase 0. |
| **Resolve by** | Phase 7 defaults; firm config before Phase 10. |

---

## OD-14 — Billing layout parsers are corpus-specific

| Field | Content |
|-------|---------|
| **Affected** | Module 06 §10; FR-BIL-01..04; §9.4 |
| **Why it matters** | Positioned-word grouping may need layout-specific rules per ledger style. |
| **Options** | (A) Generic row-grouping + review issues on failure. (B) Hard-code eCW-only. (C) Table ML model. |
| **Recommended** | **A** per doctrine (§9.4); layout-specific rules only as measured need; never LLM-primary tables. |
| **Consequences / risks** | First ledger may need eCW-specific header map (see billing spike). |
| **Blocks a phase?** | No for Phase 0–5. |
| **Resolve by** | Phase 6 (with spike findings). |

---

## OD-15 — PaddleOCR / GPU vs CPU deployment on target hardware

| Field | Content |
|-------|---------|
| **Affected** | Prototype §16; Phase 3 hardware benchmark |
| **Why it matters** | Spec says GPU optional; GTX 1060 may or may not speed English PP-OCR. |
| **Options** | (A) CPU-first for prototype stability. (B) GPU if available. (C) Force GPU. |
| **Recommended** | **A** with optional GPU experiment documented in OCR spike / Phase 3 bench. |
| **Consequences / risks** | Long medical stacks remain multi-minute (accepted in spec). |
| **Blocks a phase?** | No. |
| **Resolve by** | Phase 3. |

---

## OD-16 — PaddleOCR major version pin (measured)

| Field | Content |
|-------|---------|
| **Affected** | Phase 3; FR-EXT-05; [`ocr-spike-report.md`](./ocr-spike-report.md) |
| **Why it matters** | PaddleOCR 3.7 + Paddle 3.3.1 crashed on this Windows host (oneDNN/PIR). PaddleOCR 2.7.3 + Paddle 2.6.2 succeeded in `spikes/ocr/.venv`. |
| **Options** | (A) Pin 2.7.3/2.6.2 for Phase 3. (B) Debug/upgrade 3.x before Phase 3. (C) Swap OCR engine (conflicts with selected stack). |
| **Recommended** | **A** for initial Phase 3; schedule **B** as a follow-up spike before claiming 3.x. |
| **Consequences / risks** | Staying on 2.7 may miss 3.x accuracy/features; jumping to 3.x without pin blocks Phase 3. |
| **Blocks a phase?** | **Yes** for Phase 3 production adapter until a working pin is chosen. Does not block Phase 0. |
| **Resolve by** | Phase 3 start. |

---

## Summary table

| ID | Topic | Blocks Phase 0? | Resolve-by |
|----|-------|-----------------|------------|
| OD-01 | OCR thresholds | No | Phase 3 |
| OD-02 | Schema generation | Soft (exit) | Phase 0 |
| OD-03 | app_version | No | Phase 0 |
| OD-04 | Session scheduler | No | Phase 1 |
| OD-05 | DOCX→PDF converter | No | Phase 1–2 |
| OD-06 | CLS thresholds | No | Phase 4 |
| OD-07 | Firm gold | No (blocks 5/6/7/10 honesty) | Before Phase 5 claim |
| OD-08 | Waiver policy | No | Phase 7 |
| OD-09 | Draft assembly | No | Phase 8 |
| OD-10 | Attorney confirm export | No | Phase 9 |
| OD-11 | Module-local types | No | Phase 6/8 as needed |
| OD-12 | LLM provider | No | Post Phase 5 |
| OD-13 | Issue severity config | No | Phase 7 / 10 |
| OD-14 | Billing layouts | No | Phase 6 |
| OD-15 | OCR CPU/GPU | No | Phase 3 |
| OD-16 | PaddleOCR version pin | No (blocks Phase 3 adapter) | Phase 3 start |
