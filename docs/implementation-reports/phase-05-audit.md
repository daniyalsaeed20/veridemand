# Phase 5 Independent Audit — Deterministic Fact Extraction

**Audit date:** 2026-07-20  
**Auditor:** Fresh independent verification (not the Phase 5 implementer)  
**Method:** Commit-target verification + authoritative doctrine/contracts/module review + FactService/parser architecture inspection + FR-DET-01..06 traceability + synthetic unit/integration evidence + instrumented authority/ambiguity/lifecycle/no-reprocess/zero-LLM/sensitive-log probes + real gitignored `docs/example/` reference-package process/facts (aliases only) + gold/worksheet inspection + contract dual-regen via `check-all` + full backend/frontend clean verification

**Constraints honored:** No production code changes. No Phase 6 work. No Git tag create/move/delete. Audit probes and private aggregates lived only under gitignored `tmp/audit/`. Private filenames, extracted patient values, screenshots, and credentials were not committed. This report is left **uncommitted** for a separate closure procedure.

**Prior evidence reviewed (not trusted alone):** [`phase-05-completion.md`](./phase-05-completion.md) (`PASS WITH GAPS` on `cab86da`); Phase 3 OCR completion/hardening audits; Phase 4 completion / failed-audit / hardening / [`phase-04-hardening-audit.md`](./phase-04-hardening-audit.md) (`PASS` on `62e1828`).

---

## Final verdict

# PASS WITH GAPS

Phase 5 deterministic fact extraction at commit `cab86da303ae4340729d56a68194b92c90c4dab1` satisfies the **implementation** exit-gate behaviors audited here (critical facts present/traceable **or** queued; no silent inventing of verified placeholders; authority/ambiguity/lifecycle/no-reprocess/zero-LLM gates) with **real reference-package** evidence.

It does **not** satisfy an **honest accuracy exit**: firm-approved gold remains open (**OD-07** / acceptance-matrix **Blocking**). Therefore this commit is **not** stated as suitable for the immutable tag `phase-05-audited-pass`.

Do **not** create `phase-05-audited-pass` in this step. Do **not** begin Phase 6.

---

## Exact audited commit

| Field | Value |
|-------|-------|
| Branch | `phase-05-deterministic-facts` |
| **Audited implementation commit** | `cab86da303ae4340729d56a68194b92c90c4dab1` (`phase-05: implement deterministic fact extraction`) |
| **Current branch tip** | `55a43615865d8eeb7cdb9847dcf7bd99465dde2a` (`docs: record Phase 5 implementation commit hash in completion report`) |
| Diff `cab86da..55a4361` | **Docs only** — 1 file, 1 line in `phase-05-completion.md` |
| Working tree at audit start | Production clean (gitignored `tmp/` + `docs/example/*.{pdf,docx}` present locally) |
| Working tree after probes | Production unchanged; this report + gitignored `tmp/audit/` |

### Commit-target ruling

Tip contains only a documentation/report hash note. **Production code audited at `cab86da`.** Tip documentation used as supporting context only. No silent audit of a different code state.

### Ancestry / baseline

| Check | Result |
|-------|--------|
| Descends from `phase-04-audited-pass` | Yes (`62e1828a7a32ad0a1909c36dcfc34ebf3b40625d`) |
| Annotated tag peel | Tag object `e5dac9aa…` → commit `62e1828…` |
| Prior tags unmoved | `phase-00-pass`, `phase-01-pass`, `phase-01-audited-pass`, `phase-02-audited-pass`, `phase-04-audited-pass` |
| `phase-03-audited-pass` | Still absent in this clone (same note as Phase 4 audits) |
| `phase-05-audited-pass` | **Does not exist** (not created) |

### Diff scope (`phase-04-audited-pass..cab86da`)

33 files / +3976 / −23: FactService + registry parsers, eligibility/normalize/consolidate/status/conflicts/calculations, session fact APIs, process hook, additive contracts (`fact-types`, `issue-types`), FactsPanel + client Zod, Phase 5 tests, spike probe, completion report, Phase 4 hardening-audit doc commit on path.

**No** TimelineEvent/BillingEntry ledger construction, contradiction engine, demand drafting/export, or live LLM provider path. Contract stubs for TimelineEvent/BillingEntry remain Phase-0 schema inventory only.

Privacy: `docs/example/*.pdf|*.docx` remain gitignored and untracked.

---

## Scope result

| Check | Result |
|-------|--------|
| Branch `phase-05-deterministic-facts` | PASS |
| Tip vs implementation docs-only | PASS |
| Working tree production clean | PASS |
| Descends from Phase 4 audited tag | PASS |
| Prior tags unchanged | PASS |
| Diff limited to Phase 5 DET (+ docs) | PASS |
| No Phase 6 chronology/billing ledger | PASS |
| No contradiction engine / drafting / export | PASS |
| No live LLM provider | PASS |
| No private case docs committed | PASS |

---

## Requirement traceability (FR-DET-01..06)

| FR | Production | Contract | API/UI | Automated tests | Synthetic | Real package | Deferred | Exit-gate |
|----|------------|----------|--------|-----------------|-----------|--------------|----------|-----------|
| **FR-DET-01** Extract exact types | `registry.py` + `parsers/` runner | `fact-types.md` additive contacts/report/CPT/calc | Facts list/panel | unit parsers + integration process→facts | Spike aggregates (8 facts) | 355 deterministic facts across types | Narrative/imaging prose types deferred | Met for MVP DET catalog; billing money sparse on real OCR |
| **FR-DET-02** Normalize + raw | `normalize.py` | Fact raw/normalized/display | Display in panel | `test_fact_normalize_context.py` | Yes | Yes (raw retained) | EU↔US date policy stays warning | Met |
| **FR-DET-03** Label/context | `context.py` + negative cues | Catalog § | — | claim vs policy, DOL vs visit tests | Yes | Over-broad name/DOB on medical → conflicts | Stronger medical name disambiguation | Met with quality gap |
| **FR-DET-04** Source spans + confidence | ParserHit → Fact `source_span_ids` | `fact.md` prefer ≥1 extracted | Click → DocumentViewer | span prefix asserts; probe span_ok | rate 1.0 | rate 1.0; 0 invalid refs | Calc facts empty spans (see gaps) | Met for deterministic; calc tension noted |
| **FR-DET-05** Calcs in code | `calculations.py` Decimal | `calc.*` types | Shown as suggested | unit calc Decimal | `calc.charges_sum` in synthetic | `visit_count` + `service_date_range` only | Full ledger = Phase 6 | Met (helpers only) |
| **FR-DET-06** Amber/Red gaps/conflicts | `conflicts.py` | `extraction.missing_critical_fact` + conflict types | Issues strip in FactsPanel | conflicts/gaps unit + integration | Gap issues emitted | 6 missing-critical + 7 conflict issues | Full Phase 7 resolution UX | Met |

---

## Parser architecture

Authoritative boundary: [`FactService`](../../backend/app/services/facts/service.py) — sole Fact commit path.

Pipeline: `document_eligibility` → `filter_usable_spans` → `parse_document_spans` → `consolidate_hits` → `score_and_status` → calculations → `detect_exact_conflicts` / `create_gap_reviews` → preserve `LOCKED` → replace non-locked facts + fact-owned issues.

- Parsers return `ParserHit` candidates; they do not persist.
- API handlers in `sessions.py` delegate to FactService (no scattered regex).
- Commit barriers: session missing, generation mismatch, `deleting` flag, pre-commit hook.
- `llm_call_count` always 0; `ENABLE_LLM_SEMANTIC_EXTRACTION` logged and ignored.

### Parser inventory (`PARSER_SPECS`)

| Parser ID | Fact type |
|-----------|-----------|
| `det.client.name/dob/phone/email/address/pronouns.v1` | `client.*` |
| `det.attorney.name/phone/email.v1` | `attorney.*` |
| `det.insurer.name.v1` / `det.insured.name.v1` / `det.adjuster.name.v1` | insurer/insured/adjuster |
| `det.claim.number.v1` / `det.policy.number.v1` | claim/policy |
| `det.collision.date/time/report_number/location.v1` | `collision.*` |
| `det.liability.citation.v1` | `liability.citation` |
| `det.medical.provider/provider_phone/visit_date.v1` / `det.medical.diagnosis.icd.v1` | medical |
| `det.imaging.study_date/modality.v1` | imaging |
| `det.damages.charge/payment/adjustment/balance/specials_claimed/lien.v1` | damages |
| `det.billing.cpt.v1` | `billing.cpt` |
| `det.corr.offer_deadline/response_deadline.v1` | correspondence |

Calculations (not parsers): `calc.visit_count`, `calc.service_date_range`, `calc.charges_sum`.

---

## Authority filtering

| Check | Result |
|-------|--------|
| Excluded / template / uncertain_derivative ineligible | PASS (`eligibility.py`) |
| Primary via `is_primary_authoritative` | PASS |
| Existing demand primary verified facts | **0** (API + direct service) |
| Reclassify demand→police with safety archetype retained | Bypass blocked (synthetic + real) |
| Secondary never auto-verifies | PASS (`status.py` + service guard) |
| Unusable pages / quality flags dropped | PASS |
| Sequence not used for eligibility | PASS (not consulted) |

---

## Ambiguous classification

| Check | Result |
|-------|--------|
| `proposed` / `ambiguous` / `needs_confirmation` → `classification:ambiguous` | PASS |
| Blocks auto-verify | PASS (synthetic billing probe: none verified; all flagged) |
| Real eCW billing `classification_status=ambiguous` | Confirmed; **0** verified facts from billing alias |
| Facts UI surfaces ambiguity | PASS (`FactsPanel` reads description flag) |
| Classification PATCH does not rerun OCR | Inherited Phase 4; fact re-extract uses spans only |

---

## Context / normalization / consolidation / status

**Context:** Label cues + neighbor values + negative cues + footer/attorney/demand-amount guards. Not regex-alone. Unit tests cover DOL vs visit, claim vs policy, ICD reject, template suppression.

**Normalization:** Dates → ISO with `ambiguous_day_month_order` warning (status → needs_review). Money → `Decimal` strings; parentheses negatives. Phone → `+1` + 10 digits (US assumption — documented policy gap). Email lowercase. CPT/ICD pattern gates. Invalid → null normalized / review — no invent.

**Consolidation:** Key `(fact_type, normalized_value)`; conflicts kept separate; idempotent re-extract on real package (`357` → `357`).

**Status policy:** Critical auto-verify requires conf ≥ 0.95 **and** ≥2 spans **and** no warnings. Secondary/ambiguous/weak → needs_review. Explains reported synthetic aggregate **8 / 7 needs_review / 1 suggested / 0 verified** and real-package **0 verified**: conservative policy, not a broken status enum. Auto-verify is intentionally rare (effectively unreachable on this corpus).

---

## SourceSpan integrity

| Check | Result |
|-------|--------|
| Deterministic facts cite real `span_*` IDs | PASS (real package invalid refs = **0**; link rate **1.0**) |
| Spans belong to session documents | PASS (sampled via probe index) |
| No fabricated parser span IDs | PASS |
| Calculated facts empty `source_span_ids` | Observed (2); inputs recorded in `description` — **contract tension** vs `fact.md` “empty only if user-supplied” |

---

## Critical fields / missing-critical / conflicts / calculations

**Critical set** (`CRITICAL_FACT_TYPES`): client.name/dob/pronouns, insured/insurer name, claim/policy number, collision.date/location/report_number, medical.diagnosis, damages.specials_claimed, correspondence.offer_deadline.

| Check | Result |
|-------|--------|
| No TBD / empty / guessed Fact invent | PASS (`no_invented_placeholders`) |
| Missing → Red `extraction.missing_critical_fact` | PASS (real: **6** issues) |
| Conflicts retain all candidates; no majority winner | PASS (real: **160** conflicting facts; **7** conflict issues) |
| Conflict explanations include normalized values | Safe for review UI; not written to operational log messages |
| Calcs use Decimal; empty input → no zero Fact | PASS |
| No TimelineEvent / BillingEntry created | PASS |

**Real-package quality note:** Large `client.name` (159) and `client.dob` (80) candidate volumes with heavy conflict status indicate over-matching on medical bundles. Values are **queued**, not auto-verified — nonblocking for silent-error gate, blocking for any future accuracy claim without gold.

**Billing money:** Real package emitted **no** `damages.charge` / `billing.cpt` / `calc.charges_sum` in aggregate types (visit calcs present). eCW billing remains classification-ambiguous with weak DET money hits — gap vs FR-DET-01 breadth on this fixture class.

---

## Lifecycle / API / frontend

| Probe | Result |
|-------|--------|
| DELETE during fact commit | 204 delete; GET facts 404; no 500 |
| Concurrent extracts (×3) | All 200; no 500 |
| Stale generation barrier | Returned 0 facts; session unchanged |
| Cross-session list | Empty facts |
| Unknown fact PATCH | 404 `fact_not_found` |
| Locked fact PATCH | 409 `fact_locked` (integration) |

**Frontend:** `FactsPanel` groups by category; status CSS classes; ambiguity/secondary flags; conflicts & missing strip; click resolves span page via `listSpans` then focuses DocumentViewer. Suggested ≠ verified visually. Accessibility: button list items; prototype-reasonable. Full interactive browser highlight/zoom matrix not re-driven in this audit (code + span probe only) — **nonblocking manual gap**.

---

## No-reprocessing / zero-LLM / sensitive logs

| Check | Result |
|-------|--------|
| Re-extract patches native + OCR to raise | **0** native / **0** OCR reruns (synthetic + real) |
| Span IDs unchanged on re-extract | PASS (synthetic) |
| Synthetic re-extract latency | **~2.4 ms** (aligns with reported ~3.4 ms) |
| Real package re-extract | **~108 ms** (larger fact set; still no OCR/native) |
| `llm_call_count` | **0** even with `enable_llm_semantic_extraction=True` |
| Sentinel PII in root StreamHandler | No hits (handler captured 0 chars — structlog bypass); console JSON during probes shows session/document IDs only |

---

## Real reference-package result

**Discovery:** Present under gitignored `docs/example/`. Spike fallbacks `tmp/reference-package`, `tmp/amini`, `private/reference-package` **absent**. Completion report’s “package absent” claim is **outdated** for this workspace.

**Probe:** `tmp/audit/phase05_audit_probes.py` → `tmp/audit/phase05_audit_probes.json` (aliases only). Real OCR + LibreOffice (same approach as Phase 4 hardening package).

| Metric | Value |
|--------|------:|
| Documents | 10 aliases |
| Facts | 357 |
| Deterministic | 355 |
| Calculated | 2 |
| needs_review | 195 |
| conflicting | 160 |
| suggested | 2 |
| verified | 0 |
| Source-link rate (deterministic) | 1.0 |
| Invalid span refs | 0 |
| Process wall | ~33.9 s |
| Re-extract | ~108 ms |
| Native/OCR reruns on re-extract | 0 / 0 |
| LLM calls | 0 |
| Demand verified primary | none |
| Reclassify demand bypass blocked | yes |
| eCW billing status | ambiguous; 0 verified |
| Missing-critical issues | 6 |
| Conflict issues | 7 |
| Invented placeholders | none |

Aliases processed: police, insurer, ecw_medical, ecw_billing, long_medical, existing_demand, jackman_demand_1..3, template.

---

## Gold / lawyer worksheet

| Item | Status |
|------|--------|
| `docs/example/gold/` | Illustrative only |
| `firm_approved` | **No** (OD-07) |
| Worksheet `tmp/phase05/lawyer-verification-worksheet.json` | `pending_lawyer_confirmation`; gitignored via `tmp/` |
| Existing demand as gold answer key | Explicitly rejected in worksheet note |
| Matrix **Blocking** | Firm-approved gold for honest claim |
| Matrix **Nonblocking** | Illustrative demos if labeled |

**Ruling:** Lawyer/firm gold incomplete is **blocking for honest Phase 5 accuracy exit and for stating suitability of `phase-05-audited-pass`**. It is **not** treated as a production-code defect.

---

## Synthetic regression quality

Unit/integration cover positive/negative contexts, template/excluded, ambiguous billing, demand non-primary, delete race, locked patch, zero-LLM, Decimal calcs, conflicts/gaps. Spike fixtures are label-shaped (risk of parser-tuning to wording) — noted as nonblocking. Named full lifecycle matrix (TTL mid-parse, doc delete mid-parse, authority change mid-parse) only partially covered beyond delete-during-commit + generation barrier + concurrent extract.

---

## Performance

| Path | Observation |
|------|-------------|
| Synthetic process+facts (prior spike) | ~147 ms; re-extract ~3.4 ms |
| Audit synthetic re-extract | ~2.4 ms |
| Real package process+facts | ~33.9 s |
| Real re-extract | ~108 ms |
| OCR during fact re-extract | None |

Correctness/provenance prioritized over perf.

---

## Contracts / clean verification

| Suite | Result |
|-------|--------|
| Backend ruff format/check | PASS |
| mypy | PASS (96 files) |
| pytest | **240 passed** |
| JSON schema export ×2 | PASS |
| `contracts:check` drift | **none** |
| Frontend format/lint/typecheck | PASS |
| vitest | **12 passed** |
| Production build | PASS |
| `node scripts/check-all.mjs` | PASS |

---

## Blocking defects

**None** against the implementation exit gate (no silent verified invent; critical gaps queued; authority/ambiguity/lifecycle/LLM/reprocess gates held on audited evidence).

**Honesty / tag blockers (not code defects):**

1. **OD-07 / firm-approved gold absent** — acceptance matrix Blocking for honest claim; silent-critical-error-rate = 0 on gold **not** measurable.
2. Therefore **no** suitability statement for `phase-05-audited-pass`.

---

## Nonblocking gaps

1. Real-package over-extraction of `client.name` / `client.dob` → large conflict sets (review burden).
2. Weak DET money/CPT extraction on real eCW billing alias (classification ambiguity retained).
3. Calculated facts use empty `source_span_ids` while `fact.md` says empty only if user-supplied (inputs in description; provenance=`calculated`).
4. US `+1` phone normalization without explicit catalog country policy.
5. Conflict Issue explanations embed normalized values (appropriate for UI; ensure never copied into operational logs).
6. Auto-verify effectively unreachable on reference corpus (conservative — explain, do not “fix” by loosening).
7. Manual browser source-highlight/zoom matrix not fully re-executed this audit.
8. Sensitive-log StreamHandler probe inconclusive for structlog; console samples clean.
9. Spike still searches non-`docs/example` paths for reference package.
10. Full TTL / mid-parse authority-change barrier matrix beyond delete+generation+concurrent.

---

## Specification conflicts noted

| Conflict | Resolution used |
|----------|-----------------|
| Completion report “package absent” vs local `docs/example/` | Audited **present**; real-package acceptance executed |
| Matrix exit gate vs prototype “from the gold set” | Implementation gate audited; honest gold gate remains OD-07 |
| Calc empty spans vs `fact.md` wording | Nonblocking contract tension |

---

## Final verdict (restated)

# PASS WITH GAPS

Commit `cab86da303ae4340729d56a68194b92c90c4dab1` implements Phase 5 DET with independent synthetic and **real reference-package** evidence for no silent inventing, SourceSpan integrity on deterministic facts, authority/ambiguity safety, lifecycle barriers, no reprocessing, and zero LLM.

Firm-approved gold (**OD-07**) remains incomplete; therefore this audit does **not** claim an honest Phase 5 accuracy exit and does **not** state that the commit is suitable for `phase-05-audited-pass`.

Do **not** create the tag in this step. Do **not** begin Phase 6. Preserve this report via a separate closure procedure.
