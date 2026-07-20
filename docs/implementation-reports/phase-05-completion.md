# Phase 5 Completion Report — Deterministic Fact Extraction

**Branch:** `phase-05-deterministic-facts`  
**Verdict:** `PASS WITH GAPS`  
**Date:** 2026-07-20

## Baseline

| Field | Value |
|-------|-------|
| Phase 4 audited tag | `phase-04-audited-pass` |
| Phase 4 audited commit | `62e1828a7a32ad0a1909c36dcfc34ebf3b40625d` |
| Pre-implementation tip | `deed472` (docs: Phase 4 hardening audit) |
| Phase 5 implementation commit | `cab86da303ae4340729d56a68194b92c90c4dab1` |

Prior Phase 4 audit / hardening / hardening-audit reports are preserved and not erased.

## Requirement traceability

| FR | Implementation |
|----|----------------|
| FR-DET-01 | Parser registry + catalog parsers for dates, times, DOB, phones, emails, claim/policy/report/citation, names, currency, CPT, ICD-10 |
| FR-DET-02 | `normalize.py` retains raw; stores typed normalized + display |
| FR-DET-03 | Label/context windows in `context.py` (+ positive/negative cues) |
| FR-DET-04 | Every deterministic Fact has `source_span_ids` + scored confidence |
| FR-DET-05 | `calculate_service_ranges`, `count_visits`, `sum_money` (`calc.*` Facts, Decimal) |
| FR-DET-06 | Conflicts + `extraction.missing_critical_fact` Issues; no invented placeholders |

## Parser architecture

Authoritative service: `FactService` ([`backend/app/services/facts/service.py`](../../backend/app/services/facts/service.py)).

Pipeline: eligible docs → usable spans → registry parsers → consolidate → status policy → atomic commit → conflict/gap Issues.

Parsers never persist outside `FactService`. Re-run via `POST .../facts/extract` reuses published spans (no OCR/PDF rerun).

## Parser catalogue implemented

Catalog version `0.1-provisional` rows under `det.*.v1` for identity, claim/insurer, collision/citation, medical/imaging exact, billing money/CPT, correspondence deadlines — see [`docs/modules/05-fact-parser-catalog.md`](../modules/05-fact-parser-catalog.md) and [`backend/app/services/facts/registry.py`](../../backend/app/services/facts/registry.py).

## Fact types implemented (MVP DET)

Including additive Phase 5 types:

- Contacts: `client.phone`, `client.email`, `attorney.phone`, `attorney.email`, `medical.provider_phone`
- Report: `collision.report_number`
- Codes/calc: `billing.cpt`, `calc.visit_count`, `calc.service_date_range`, `calc.charges_sum`
- Plus catalog MVP types exercised by parsers (claim/policy, collision.date, names, money lines, ICD-10, etc.)

User-supplied `demand.*` types are never invented.

## Context rules

Same-line preference; ±1 neighbor line; max 80 chars; footer y-threshold; template/example cues; attorney letterhead vs claimant phone; demand amount vs medical charge; claim vs policy vs report vs citation label separation.

## Normalization policy

Dates → `YYYY-MM-DD` (ambiguous day/month → warning / needs_review, not silent EU↔US invent). Currency → Decimal string. Phone → `+1##########`. Email lowercase. CPT 5-digit. ICD-10 pattern. Invalid → no Fact invent; review or drop candidate.

## Status / criticality policy

Conservative auto-verify. Secondary, classification-ambiguous, page-quality-weak, and most critical single-source values → `needs_review` / `suggested`. Conflicts → `conflicting`. OCR span confidence informs but does **not** equal fact confidence.

## Exact-conflict policy

Multiple normalized values for same `fact_type` retained; Issue emitted (`identity.*` / `claim.*` / `collision.*` / etc.). No silent winner.

## Authority filtering

Uses `is_primary_authoritative` + explicit secondary path. Templates / excluded / disabled demands supply no Facts. Secondary suggestions marked `authority:secondary` and never auto-verify or override primary.

## Ambiguous-classification handling

`classification_status` in `{proposed, ambiguous, needs_confirmation}` stamps `classification:ambiguous` and blocks auto-verify even when primary (eCW billing scenario).

## FR-CLS-04 handoff

Provider / insurer / claimant / date-range metadata Facts owned by Phase 5 DET (not Phase 4 classification leftovers). Document-level classification remains separate from verified case Facts.

## APIs and frontend

- `GET /api/v1/sessions/{id}/facts`
- `POST /api/v1/sessions/{id}/facts/extract`
- `PATCH /api/v1/sessions/{id}/facts/{fact_id}`
- Process stage emits `fact.extracting` / `fact.extracted` after classification
- Facts panel: grouped list, status, provenance, ambiguity/secondary flags, conflict/missing Issues, click → DocumentViewer highlight

## Automated test totals

| Suite | Count | Notes |
|-------|------:|-------|
| Backend | **240** | Phase 4 baseline was 213; +27 Phase 5 |
| Frontend | **12** | Phase 4 baseline was 9; +3 Facts panel |

## Local reference-package aggregate results

Local Amini/reference package **absent** (same gap as Phase 4 completion). Synthetic acceptance probe: [`spikes/phase05_fact_acceptance_probe.py`](../../spikes/phase05_fact_acceptance_probe.py) → gitignored `tmp/phase05/aggregates.json`.

Representative synthetic aggregates:

| Metric | Value |
|--------|------:|
| Documents | 10 aliases |
| Facts | 8 |
| needs_review | 7 |
| suggested | 1 |
| verified | 0 |
| Source-link rate (deterministic) | 1.0 |
| Parse wall | ~147 ms |
| Re-extract | ~3.4 ms |
| OCR events during fact stage | 0 |
| LLM calls | 0 |
| Demand/template docs present | 2 |
| Invented placeholders | none |

## Gold-set status

Illustrative only (`docs/example/gold/`). **Not** `firm_approved` (OD-07). Honest firm exit blocked.

## Lawyer-verification worksheet

Generated at `tmp/phase05/lawyer-verification-worksheet.json` (gitignored) with `pending_lawyer_confirmation`. No private excerpts committed.

## Source-link evidence

Deterministic Facts require `source_span_ids`; unit/integration assert `span_` prefixes; UI navigates to page + highlight polygons. Synthetic visual only — no patient screenshots committed.

## No-reprocessing evidence

`POST .../facts/extract` after process completes in ~3 ms without OCR events; process fact stage does not re-invoke OCR/PDFium/LibreOffice.

## Zero-LLM evidence

`FactService.llm_call_count` remains 0 even if `ENABLE_LLM_SEMANTIC_EXTRACTION=true`. Probe and unit test assert zero calls. No LLM fallback on parser miss.

## Performance

Synthetic multi-doc package process+facts ~147 ms wall (local). Consolidation included in extract. Memory not separately profiled.

## Known limitations / gaps

1. Firm-approved gold missing (OD-07) → cannot claim honest Phase 5 accuracy exit.
2. Real Amini/Jackman reference package not present in this workspace.
3. Native PDF fixtures may yield fewer labeled hits than OCR pages with rich text; parsers are label-gated by design.
4. Full Phase 7 review-resolution UX deferred.
5. FR-DET-05 calcs are helpers only — no TimelineEvent / BillingEntry ledger (Phase 6).
6. Manual rectangle `POST .../source-spans/manual` not required for MVP PATCH path (user edits via PATCH value).

## Deferred Phase 6/7 work

Chronology UI, billing ledger reconciliation, semantic consolidation, full issue resolution workflow, demand drafting/export.

## Specification conflicts

| Conflict | Resolution |
|----------|------------|
| FR-DET-01 phones/emails vs empty `fact-types.md` | Additive types (catalog §4.3 allows) |
| Report numbers vs `claim.number` overload | Additive `collision.report_number` |
| Missing-critical Issue type absent | Additive `extraction.missing_critical_fact` |
| `is_authoritative_evidence` False for secondary when `exclude_from_drafting` | Eligibility uses explicit secondary path |

Recorded for readiness; contracts updated additively; no silent doctrine rewrite.

## Exit-gate evidence

| Gate | Evidence |
|------|----------|
| Critical exact facts present/traceable **or** queued | Gap Issues + needs_review; no TBD/0 invent |
| Silent inventing = 0 | Tests + probe |
| No LLM extraction | Zero-call tests |
| Authority suppression | Unit + integration |
| Ambiguity retained | Integration test |
| Lifecycle races | Delete-during-extract integration |
| check-all / contracts dual regen | Pass |

## Final verdict

# PASS WITH GAPS

Implementation of Phase 5 DET MVP is complete with automated evidence above Phase 4 baselines. Honest firm-approved gold exit remains blocked (OD-07). Do **not** create `phase-05-audited-pass` in this step. Do **not** begin Phase 6.
