# VeriDemand Module Documentation Index

Individual module design docs derived from [`../prototype_documentation.md`](../prototype_documentation.md).

**Process controller (use this to generate/update module docs):**  
[`MODULE_DOC_GENERATION.md`](./MODULE_DOC_GENERATION.md)

**Field-level contracts SoT:**  
[`../contracts/README.md`](../contracts/README.md) (`contracts_version` 0.1)

**Developer brief:** For any module, open (1) [`../prototype_documentation.md`](../prototype_documentation.md), (2) that module’s `NN-*.md`, (3) the contracts listed in its header `Contracts` row, and (4) any linked addendum (`03-ocr-thresholds`, `05-fact-parser-catalog`, `ui-notes`, gold). **If prose conflicts with `docs/contracts/`, contracts win.**

**Illustrative gold keys (examples only):**  
[`../example/gold/README.md`](../example/gold/README.md) — shape only; Phase 10 runner → [module 12](./12-evaluation-demonstration.md)

**OCR / extraction thresholds (provisional):**  
[`03-ocr-thresholds.md`](./03-ocr-thresholds.md)

**Fact parser catalog (provisional):**  
[`05-fact-parser-catalog.md`](./05-fact-parser-catalog.md)

**Light UI notes (implementer SoT for panels/recovery):**  
[`ui-notes.md`](./ui-notes.md)

**API error codes:**  
[`../contracts/error-codes.md`](../contracts/error-codes.md)

## Phase ↔ Module ↔ UI crosswalk

**Module N ≠ Phase N.** Use this table; do not invent a third numbering map.

| Roadmap phase | Module file(s) | UI step (§13.2 / ui-notes) | Notes |
|---------------|----------------|----------------------------|--------|
| Phase 0 | [00](./00-repository-and-contracts.md) | — (app shell / health) | Contracts + harness scaffold |
| Phase 1 | [01](./01-session-and-workspace.md), [02](./02-upload-validation-normalization.md) | Step 1 Documents (upload) | Session + upload |
| Phases 2–3 | [03](./03-page-analysis-and-text-extraction.md) | Step 1 Documents (pages/quality) | Native + OCR critical path |
| Phase 4 | [04](./04-document-classification-and-sequencing.md) | Step 1 Documents (classify/sequence) | |
| Phase 5 | [05](./05-deterministic-fact-extraction.md) | Step 2 Facts | Extraction MVP (no LLM) |
| Phase 6 | [06](./06-chronology-and-billing.md); optional [11](./11-llm-semantic-consolidation-optional.md) | Step 3 Timeline & Billing | Module 11 is optional / out of numeric order |
| Phase 7 | [07](./07-issue-and-contradiction-engine.md), [08](./08-human-review-and-manual-intervention.md) | Step 4 Issues (+ Facts review) | |
| Phase 8 | [09](./09-demand-generation.md) | Step 5 Demand | |
| Phase 9 | [10](./10-verification-preflight-and-export.md) | Step 6 Preflight | **Module 10 = Phase 9** |
| Phase 10 | [12](./12-evaluation-demonstration.md) | — (CLI / report; not a workspace step) | Eval runner; gold **shape** stays in `docs/example/gold/` |

| UI step | Primary modules |
|---------|-----------------|
| 1 Documents | 02, 03, 04 |
| 2 Facts | 05, 08 |
| 3 Timeline & Billing | 06 |
| 4 Issues | 07, 08 |
| 5 Demand | 09 |
| 6 Preflight | 10 |

## Module → primary contracts

| Module | Primary contracts |
|--------|-------------------|
| 00 | All entities as schema pack; `AppSettings`, `HealthResponse`, enums, taxonomies, `error-codes` |
| 01 | `CaseSession`, `SessionStatus`, session `error-codes` |
| 02 | `Document`, `DocumentFileType` / `DocumentStatus`, upload `error-codes` |
| 03 | `DocumentPage`, `SourceToken`, `SourceSpan`, `PageRoute` / `ExtractionMethod`, `extraction.*`, AppSettings OCR knobs |
| 04 | `Document` classification fields, `DocumentClassification` |
| 05 | `Fact`, `Issue` (gaps), `fact-types`, `FactStatus` (+ parser catalog) |
| 06 | `TimelineEvent`, `BillingEntry`, `TimelineEventType`, `billing.*`, `Issue` |
| 07 | `Issue`, `issue-types`, `IssueSeverity` / `IssueStatus` |
| 08 | `UserDecision`, `DecisionAction`, `Fact` / `Issue` / `SourceSpan`, `ReviewState` |
| 09 | `DraftSection`, `DraftSectionType`, `draft.*` |
| 10 | `PreflightReport`, `ExportResult`, `StatementSupportLabel`, export `error-codes` |
| 11 | Consumes `Fact` / `SourceSpan` / `fact-types` (optional; merges into `Fact`) |
| 12 | Gold shape + `fact-types` / `issue-types`; scores `Fact` / `Issue` / preflight / export |

## Build order

| # | Module | File | Status |
|---|--------|------|--------|
| 00 | Repository and Contracts | [00-repository-and-contracts.md](./00-repository-and-contracts.md) | design |
| 01 | Session and Workspace | [01-session-and-workspace.md](./01-session-and-workspace.md) | design |
| 02 | Upload, Validation, Normalization | [02-upload-validation-normalization.md](./02-upload-validation-normalization.md) | design |
| 03 | Page Analysis and Text Extraction | [03-page-analysis-and-text-extraction.md](./03-page-analysis-and-text-extraction.md) | design |
| 04 | Document Classification and Sequencing | [04-document-classification-and-sequencing.md](./04-document-classification-and-sequencing.md) | design |
| 05 | Deterministic Fact Extraction (MVP) | [05-deterministic-fact-extraction.md](./05-deterministic-fact-extraction.md) | design |
| 06 | Chronology and Billing | [06-chronology-and-billing.md](./06-chronology-and-billing.md) | design |
| 07 | Issue and Contradiction Engine | [07-issue-and-contradiction-engine.md](./07-issue-and-contradiction-engine.md) | design |
| 08 | Human Review and Manual Intervention | [08-human-review-and-manual-intervention.md](./08-human-review-and-manual-intervention.md) | design |
| 09 | Demand Generation | [09-demand-generation.md](./09-demand-generation.md) | design |
| 10 | Verification, Preflight, and Export | [10-verification-preflight-and-export.md](./10-verification-preflight-and-export.md) | design |
| 11 | LLM Semantic Consolidation *(optional)* | [11-llm-semantic-consolidation-optional.md](./11-llm-semantic-consolidation-optional.md) | deferred / design |
| 12 | Evaluation Demonstration | [12-evaluation-demonstration.md](./12-evaluation-demonstration.md) | design |

## Notes

- Method/function names in module docs are **proposed design** until code exists.
- Entity field shapes live in [`../contracts/`](../contracts/README.md) — do not fork them in module docs.
- Queue SoT is `Issue`; `ReviewItem` / `FactGroup` / `FactReview` are ephemeral (see contracts README).
- Module `11` is optional and not required for the extraction MVP.
- Canonical doctrine lives in [`../prototype_documentation.md`](../prototype_documentation.md) (wins over historical `.docx`).

## Quick start for agents

```text
Using docs/modules/MODULE_DOC_GENERATION.md as the process controller,
generate or update the next module document as requested.
Source of truth: docs/prototype_documentation.md
Field contracts: docs/contracts/
Always open the module’s Contracts row + relevant addenda.
Consult the Phase ↔ Module ↔ UI crosswalk in docs/modules/README.md (Module N ≠ Phase N).
```

## Changelog

| Date | Change |
|------|--------|
| 2026-07-19 | Phase↔Module↔UI crosswalk; module 12; Issue queue SoT notes |
| 2026-07-19 | Polish: module 05 Contracts includes `issue.md`; index changelog added |
