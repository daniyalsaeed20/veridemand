# Gold Answer Keys (Illustrative)

**Purpose:** Define how evaluation “gold” answer keys are structured and store **example** keys for the sample files under [`docs/example/`](../).

**Ownership split:** This folder owns gold **shape** and illustrative filled keys. The Phase 10 gold **runner**, metrics aggregation, blind-review packet, and demo script are owned by [`../../modules/12-evaluation-demonstration.md`](../../modules/12-evaluation-demonstration.md).

## Important constraint

`docs/example/` is an **illustrative reference corpus** for demos and evaluation design only. It is:

- **Not** the product’s permanent dataset  
- **Not** a claim that all real cases look like this package  
- **Not** authoritative legal truth or a lawyer-final answer key  

Gold files here teach *what a gold key looks like* and how Phase 5+ exit gates can be tested. Real firm evaluation should copy [`GOLD_CASE_TEMPLATE.md`](./GOLD_CASE_TEMPLATE.md) into a controlled location and fill it with firm-approved values for that matter.

## How to use gold in tests

| Section | Pass criterion |
|---------|----------------|
| **Must-find** | Fact present with correct `normalized_value` **and** a source span, **or** explicitly Amber/Red queued (`todo_verify` / `needs_review`) — never silently wrong |
| **Must-surface** | Listed `issue_type` appears in the review queue (`Issue` records) |
| **Must-queue** | Critical gaps produce `Issue`s (and/or `Fact.status` needs review), not invented fills |
| **Must-not-invent** | System does not fabricate these values |
| **Export blockers** | Final export blocked while these remain open (when applicable) |

Use `fact_type` / `issue_type` values from [`docs/contracts/fact-types.md`](../../contracts/fact-types.md) and [`docs/contracts/issue-types.md`](../../contracts/issue-types.md).

**Evidence vs demand draft:** An uploaded existing demand is **not** default authoritative evidence (FR-CLS-06). Demand DOCX files in the example folder are primarily **comparison / planted-defect fixtures**.

## Privacy

- Do not dump full medical narratives or unnecessary PII into gold docs.  
- Prefer placeholders or values already noted in the prototype Appendix G.  
- Keep example binaries and gold keys out of public repos and out of default LLM/logging pipelines.

## Index

| File | Role |
|------|------|
| [GOLD_CASE_TEMPLATE.md](./GOLD_CASE_TEMPLATE.md) | Reusable blank template for **any** future matter |
| [amini-illustrative.md](./amini-illustrative.md) | Example filled gold for the Amini sample evidence package |
| [draft-defect-fixtures.md](./draft-defect-fixtures.md) | Lightweight draft-hygiene fixtures (other sample DOCX demands) |

## Changelog

| Date | Change |
|------|--------|
| 2026-07-18 | Initial illustrative gold pack (Pass 2) |
| 2026-07-19 | Ownership split: shape here; Phase 10 runner/metrics → module 12 |
