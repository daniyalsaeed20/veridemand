# VeriDemand Shared Contracts

**contracts_version:** `0.1`  
**Status:** design (Markdown SoT for field shapes; no codegen in this pack)

## Role

| Document | Role |
|----------|------|
| [`../prototype_documentation.md`](../prototype_documentation.md) | Product doctrine and architecture SoT |
| **This folder (`docs/contracts/`)** | **Field-level contracts SoT** — entity shapes, enums, taxonomies, API error codes |
| [`../modules/*.md`](../modules/) | Module design and flows; must not redefine field shapes |

When implementing Pydantic/Zod models, implement against these Markdown contracts.

**Schema mirror path (until codegen exists):** Markdown contracts → Pydantic models (canonical runtime) → hand-maintained Zod mirrors in the frontend. Do not invent a second field shape in TypeScript. When CI generation exists, regenerate Zod from the Pydantic/JSON Schema export instead of editing mirrors by hand.

## Global rules

1. **Opaque IDs** — string IDs with prefixes; never expose filesystem paths in API payloads.
2. **ID prefixes** — `ses_`, `doc_`, `page_` (optional compound), `tok_`, `span_`, `fact_`, `issue_`, `evt_`, `bil_`, `draft_`, `sec_`, `para_`, `dec_`, `exp_`, `preflight_`, `art_`, `find_`.
3. **Coordinates** — normalized page space, origin top-left, values in `[0, 1]` (see §7.3 of the prototype).
4. **Datetimes** — ISO-8601 UTC with `Z` suffix in JSON examples.
5. **Money** — JSON strings with decimal representation (e.g. `"1234.56"`), never binary floats as source of truth.
6. **Dates (calendar)** — normalized as `YYYY-MM-DD` where typed; preserve `raw_value` on facts.
7. **No PII from corpus** — examples in this folder are synthetic/anonymous only.
8. **Taxonomies are additive** — new `fact_type` / `issue_type` values may be added; do not silently rename without a changelog entry.

## Index

### Enums and taxonomies

| Doc | Contents |
|-----|----------|
| [enums.md](./enums.md) | Closed enums (`SessionStatus`, `FactStatus`, …) |
| [fact-types.md](./fact-types.md) | Canonical `fact_type` catalog (Appendix A) |
| [issue-types.md](./issue-types.md) | Canonical `issue_type` catalog (Appendix B) |
| [error-codes.md](./error-codes.md) | API `error_code` catalog + envelope |

### Entities

| Doc | Entity |
|-----|--------|
| [entities/app-settings.md](./entities/app-settings.md) | `AppSettings` |
| [entities/case-session.md](./entities/case-session.md) | `CaseSession` |
| [entities/document.md](./entities/document.md) | `Document` |
| [entities/document-page.md](./entities/document-page.md) | `DocumentPage` |
| [entities/source-token.md](./entities/source-token.md) | `SourceToken` |
| [entities/source-span.md](./entities/source-span.md) | `SourceSpan` |
| [entities/fact.md](./entities/fact.md) | `Fact` |
| [entities/issue.md](./entities/issue.md) | `Issue` |
| [entities/timeline-event.md](./entities/timeline-event.md) | `TimelineEvent` |
| [entities/billing-entry.md](./entities/billing-entry.md) | `BillingEntry` |
| [entities/draft-section.md](./entities/draft-section.md) | `DraftSection` |
| [entities/user-decision.md](./entities/user-decision.md) | `UserDecision` |
| [entities/preflight-report.md](./entities/preflight-report.md) | `PreflightFinding` / `PreflightReport` |
| [entities/export-result.md](./entities/export-result.md) | `ExportResult` / `ExportArtifact` |
| [entities/health-response.md](./entities/health-response.md) | `HealthResponse` |

## Naming notes

| Canonical contract name | Deprecated / informal alias | Meaning |
|-------------------------|----------------------------|---------|
| `Fact` | `FactCandidate` (**do not use in new APIs**) | Same entity; use `Fact` + `FactStatus` for lifecycle |
| `SessionStatus` | `active` (**never emit**) | Use precise workflow states from [enums.md](./enums.md) / prototype §5.1 |
| `DocumentFileType` | module `DocumentType` (file kinds) | File MIME/extension enum — not `DocumentClassification` |

## Derived / ephemeral types (not in `entities/`)

These names appear in module design docs as helpers or UI projections. They are **not** persisted session entities and must not get separate Pydantic/Zod entity files.

| Name | Role | Maps to |
|------|------|---------|
| `ReviewItem` | Optional API/UI view-model for the review queue | Projection over [`Issue`](./entities/issue.md) (+ optional linked [`Fact`](./entities/fact.md)s needing review). Same `issue_` ids. `GET /issues` returns `Issue` (or an equivalent projection). |
| `FactGroup` | Extraction-time grouping of duplicate/conflict candidates | Ephemeral helper; feeds `IssueService` / updates `Fact` — never a contracted entity |
| `FactReview` | Extraction-time Amber/Red gap payload | Ephemeral helper that **creates or updates** an `Issue` (and may set `Fact.status`) |

Session SoT for the queue remains **`Issue`**. Upstream modules that “emit review items” create `Issue` records.

## Related living artifacts

- Illustrative gold answer keys (sample eval only): [`../example/gold/README.md`](../example/gold/README.md)
- Evaluation runner / metrics (Phase 10): [`../modules/12-evaluation-demonstration.md`](../modules/12-evaluation-demonstration.md)
- OCR / native-routing thresholds (provisional): [`../modules/03-ocr-thresholds.md`](../modules/03-ocr-thresholds.md)

## Changelog

| Version | Date | Change |
|---------|------|--------|
| 0.1 | 2026-07-18 | Initial shared contracts pack (Pass 1) |
| 0.1 | 2026-07-18 | AppSettings: additive native/OCR threshold knobs (Pass 3) |
| 0.1 | 2026-07-18 | API error-codes catalog (Pass 5) |
| 0.1 | 2026-07-19 | PreflightReport, ExportResult; DecisionAction / FindingSeverity / ExportKind enums (SoT backfill) |
| 0.1 | 2026-07-19 | Phase 9 labels on preflight/export; ephemeral types; SessionStatus never-emit `active`; FactCandidate deprecated; schema-mirror path |
| 0.1 | 2026-07-19 | Add `route_not_found` API error code for unknown routes (Phase 0 closure) |
