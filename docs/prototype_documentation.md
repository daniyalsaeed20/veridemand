# Evidence-Grounded Demand Letter Automation Prototype

**Product Requirements and Technical Specification**

**Version 0.2 | Extraction Policy Revision | July 2026**

Prepared as a modular implementation foundation for a lawyer/paralegal demand-letter workflow prototype.

> **Source of truth:** This Markdown file is the canonical specification. The Word file `docs/prototype_documentation.docx` is a historical v0.1 snapshot and should not be edited further for product decisions.

## Core Product Thesis

The application must not behave like a generic chatbot that reads files and writes a letter. It must build a traceable evidence workspace, surface uncertainty and contradictions, obtain user decisions where needed, and generate a demand letter only from approved facts.

| Field | Value |
|-------|-------|
| Document status | Canonical specification for prototype implementation (Markdown source of truth) |
| Primary users | Personal-injury lawyers and paralegals |
| Primary use case | Motor-vehicle bodily-injury demand letters |
| Prototype persistence | Runtime/session only; refresh may restart the case |
| Primary corpus assumption | About 90% of packages resemble `docs/example/`: mixed scanned typed PDFs plus some digital EMR/billing exports. Police reports, insurer letters, and long clinical stacks are often OCR-first. Handwriting is uncommon (~1% of cases; usually 2–3 pages) and handled by manual review. |
| Approval model | Human-in-the-loop; critical issues block final export until resolved or explicitly waived |
| Extraction policy | Native text and lightweight OCR plus deterministic parsers and human review are the primary extraction path. The LLM is **not** the primary extractor. |

## Document Control

| Version | Date | Status | Purpose |
|---------|------|--------|---------|
| 0.1 | July 2026 | Foundation Draft | Defined the prototype product, architecture, modules, data contracts, phased build plan, and acceptance gates (Word). |
| 0.2 | July 2026 | Extraction Policy Revision | Markdown becomes source of truth. Elevates OCR/deterministic/manual extraction; demotes LLM-as-extractor; aligns corpus assumptions and roadmap with `docs/example/`. |

### Document changelog (v0.2)

- Declared this Markdown file the canonical source of truth; Word retained as historical v0.1.
- Reframed corpus assumptions for OCR-heavy packages (~90% like `docs/example/`; ~1% limited handwriting).
- Defined extraction accuracy as: critical fields correct **or** explicitly queued — never silently wrong.
- Added principle: LLM is not the primary extractor; full-PDF LLM extraction is a non-goal.
- Retitled §8.6 as optional/deferred; Phase 5 is the extraction MVP without LLM.
- Marked Phase 3 (OCR) as critical path; Phase 8 prefers docxtpl export before TipTap polish.
- Noted PaddleOCR + pypdfium2 as load-bearing; TipTap secondary; firm DOCX letters may need template derivation.
- Refreshed Appendix G against the actual `docs/example/` inventory.
- **2026-07-19 SoT tighten:** §13 SoT split (narrative vs `ui-notes` / `error-codes`); §18 Phase↔Module↔UI crosswalk pointer; Phase 10 → module 12; suggested `Fact` / `Issue` wording in §8.5.
- **2026-07-19 polish:** Remaining “review item” vernacular normalized to review-queue `Issue` / `Issue`.

### How to Use This Specification

Implement the prototype phase by phase. Each phase has a defined objective, dependencies, deliverables, test requirements, and an exit gate. Do not begin a dependent phase until the prior phase exit gate is satisfied. The architecture intentionally separates deterministic processing, OCR, optional LLM reasoning, human review, drafting, and final validation so that each component can be improved independently.

### Contents

1. [Executive Summary](#1-executive-summary)
2. [Product Vision, Goals, and Principles](#2-product-vision-goals-and-principles)
3. [Prototype Scope and Assumptions](#3-prototype-scope-and-assumptions)
4. [User Roles and Core User Journeys](#4-user-roles-and-core-user-journeys)
5. [End-to-End Workflow](#5-end-to-end-workflow)
6. [System Architecture and Technology Stack](#6-system-architecture-and-technology-stack)
7. [Core Data Model and Evidence Provenance](#7-core-data-model-and-evidence-provenance)
8. [Functional Modules and Requirements](#8-functional-modules-and-requirements)
9. [OCR and Document Processing Strategy](#9-ocr-and-document-processing-strategy)
10. [LLM Responsibilities and Contracts](#10-llm-responsibilities-and-contracts)
11. [Human Review and Manual Intervention](#11-human-review-and-manual-intervention)
12. [Demand Letter Generation and Validation](#12-demand-letter-generation-and-validation)
13. [User Interface Specification](#13-user-interface-specification)
14. [API and Backend Contract](#14-api-and-backend-contract)
15. [Security, Privacy, and Prototype Safeguards](#15-security-privacy-and-prototype-safeguards)
16. [Performance and Hardware Profile](#16-performance-and-hardware-profile)
17. [Testing, Evaluation, and Human Baseline Comparison](#17-testing-evaluation-and-human-baseline-comparison)
18. [Modular Implementation Roadmap](#18-modular-implementation-roadmap)
19. [Risks, Limitations, and Future Expansion](#19-risks-limitations-and-future-expansion)

Appendices: [Fact Taxonomy](#appendix-a---canonical-fact-taxonomy), [Issue Taxonomy](#appendix-b---issue-taxonomy), [Repository Structure](#appendix-c---suggested-repository-structure), [Configuration](#appendix-d---prototype-configuration-defaults), [Definition of Done](#appendix-e---definition-of-done-checklist), [References](#appendix-f---research-and-engineering-references), [Source Corpus](#appendix-g---source-corpus-note)

---

## 1. Executive Summary

The prototype will transform a collection of case documents into an evidence-grounded, user-reviewed demand letter. Users will upload police reports, medical records, bills, imaging reports (often embedded inside medical bundles), insurer correspondence, photographs, liens, wage-loss material, existing demand templates, and related records. The system will extract text and locations (native when usable, OCR when not), classify and sequence documents, identify key facts via deterministic parsers with human review, build a chronology and billing summary, detect contradictions and missing information, and present concerns in a review queue. After the lawyer or paralegal verifies the evidence, the system will draft and validate a demand letter and export an editable DOCX.

The prototype is intentionally session-based. It does not require a database, permanent case storage, firm-wide authentication, billing, or production case management. Original files and derived data may be held only during the active runtime session and deleted when the session expires or the process stops.

### Success Definition

The prototype succeeds when a user can upload a representative bodily-injury case package, inspect every important fact at its exact source location, resolve uncertainty and contradictions, generate a professionally structured demand letter, and receive a preflight report showing that names, dates, amounts, treatment facts, exhibits, and narrative statements are supported.

**Extraction accuracy (operational definition):** A critical field (identity, claim/policy numbers, date of loss, key amounts, codes) is considered successful when it is either (a) correct and linked to a source span, or (b) explicitly Amber/Red in the review queue for user completion. Silent wrong values are failures. Prefer this definition over raw OCR word-error rate or “LLM extracted everything.”

### 1.1 Why the Workflow Is Feasible

The reference corpus in `docs/example/` and lawyer operational feedback indicate that about **90%** of packages resemble that set: mixed **scanned typed** PDFs (police reports, insurer letters, long clinical/chiro stacks) plus some **digitally generated** EMR and billing exports. On those packages, police pages, insurer scans, and long facsimile medical PDFs are often **OCR-first**; native PDF text is used when page usability heuristics say it is reliable (for example, some eCW exports).

Handwritten content is uncommon — roughly **1%** of cases, usually limited to two or three pages. Those values are completed by manual review (optional vision-model crop suggestion only). The application does not need a universal handwriting-recognition system in the first version, and it does **not** need LLM-based full-document extraction for the common path.

### 1.2 Product Boundary

The product is an evidence-review and drafting assistant. It does not independently determine liability, medical causation, legal strategy, or settlement value. It may propose facts, issues, summaries, and language, but a user must review critical findings and approve the final demand.

---

## 2. Product Vision, Goals, and Principles

### 2.1 Vision

Create a legal drafting workspace that is faster and more verifiable than repeatedly uploading documents to a general-purpose chatbot. The differentiator is not merely polished prose; it is evidence traceability, structured review, contradiction detection, deterministic calculations, and export controls.

### 2.2 Prototype Goals

- **G1 — Source traceability.** Every case-specific fact must link to one or more source spans containing document ID, page number, text excerpt, and visual coordinates.
- **G2 — Reliable extraction.** Prefer native text when usable; use lightweight open-source OCR when native text is not usable; complete gaps with manual review. Success means critical fields are correct **or** explicitly queued — never silently wrong.
- **G3 — Controlled AI.** When an LLM is used (optional for semantics/drafting/verification), it must use known source and fact IDs and may not become the system of record. The LLM is **not** the primary data extractor.
- **G4 — Human oversight.** The application must identify what it cannot safely determine and ask targeted questions rather than guessing.
- **G5 — Accurate calculations.** Visits, dates, charges, payments, balances, totals, durations, and exhibit counts must be calculated or validated programmatically.
- **G6 — Modular build.** Document processing, evidence extraction, issue detection, review, drafting, and export must be independently testable.
- **G7 — Demonstrable value.** The prototype must support measurable comparison with the existing manual/chatbot workflow.

### 2.3 Non-Negotiable Design Principles

| Principle | Meaning |
|-----------|---------|
| Evidence before prose | Facts and evidence links are created and reviewed before letter drafting. |
| No silent conflict resolution | Conflicting sources remain visible until the user resolves or explicitly waives the issue. |
| No unsupported factual sentence | Every case-specific factual sentence in the final draft must map to approved facts. |
| Deterministic where possible | Identity fields, dates, currency, calculations, counts, placeholders, and exact-value contradictions should be handled by code. |
| LLM is not the primary extractor | Default path: native/OCR → deterministic parsers → cross-checks → human review. Do not send full PDFs to an LLM to extract the case. Optional later LLM use is limited to classification ambiguity, semantic consolidation on selected spans, semantic issues, drafting, and verification. |
| Uncertainty is a feature | Low-confidence or incomplete results create review-queue `Issue`s rather than false certainty. |
| Prototype simplicity | No database or permanent storage until the evidence-to-demand engine is proven. |
| Free/open extraction tooling | Prefer open-source/free libraries for OCR and parsing; do not use paid document-AI services in the prototype. |

---

## 3. Prototype Scope and Assumptions

### 3.1 In Scope

- Motor-vehicle bodily-injury demand-letter workflow.
- PDF, scanned PDF, DOCX, JPG, PNG, and TIFF uploads.
- Native PDF extraction with coordinates when usable.
- OCR for scanned typed pages and printed forms (load-bearing for the reference corpus).
- Limited handwriting handling through manual review and optional vision-LLM crop interpretation.
- Document classification, logical sequencing, and user correction.
- Deterministic fact extraction, evidence linking, chronology, treatment summary, and billing ledger.
- Contradiction, inconsistency, missing-document, placeholder, and calculation checks.
- Human fact approval and issue resolution.
- Demand generation from an approved template and approved facts.
- DOCX export and optional PDF preview.
- Evaluation dashboard or test report for accuracy, traceability, review effort, and turnaround time.

### 3.2 Explicitly Out of Scope for the First Prototype

- Permanent case database or firm-wide matter management.
- User accounts, multi-tenant authentication, billing, subscriptions, and permissions administration.
- Client portal, e-signatures, insurer email delivery, calendaring, or task management.
- Automated legal research or independent selection of legal authorities.
- Autonomous settlement valuation or claims strategy.
- Guaranteed interpretation of illegible handwriting or damaged documents.
- **LLM-first or full-document LLM extraction** as the primary evidence pipeline.
- Paid cloud document-AI / document-intelligence services.
- High-concurrency production deployment.
- Long-term audit retention and production compliance certification.

### 3.3 Representative Document Profile

| Category | Typical form (reference corpus) | Primary method | Fallback |
|----------|----------------------------------|----------------|----------|
| Medical records | Digital EMR exports and/or long scanned clinical/chiro stacks | Native when usable; OCR for scans | Manual page review |
| Medical bills/ledgers | Digital claim-level CPT ledgers or scanned typed sheets | Word coordinates + row grouping when text exists | OCR and manual confirmation |
| Police reports | Printed structured form plus narrative (often image/scanned) | OCR (often OCR-first) | Field review |
| Insurance correspondence | Typed or scanned one-page letters | OCR when scanned; native when usable | Manual correction |
| Imaging reports | Often **embedded** in medical bundles, not always a standalone PDF | Text/OCR within parent document | Manual confirmation |
| Provider intake forms | Printed form with limited handwriting (~1% of cases) | OCR printed labels | User fills handwritten values |
| Demand templates/drafts | Firm DOCX letters (completed or near-completed) | python-docx; derive/adapt a docxtpl template from firm style | User edits template |

### 3.4 Reference Corpus Layout (`docs/example/`)

`docs/example/` is an **illustrative** sample package for demos and evaluation design. It is **not** the product’s permanent dataset and does not claim that all real matters look like this set.

The sample folder contains nine files (~12 MB):

- **One illustrative end-to-end evidence package (Amini / DOI 03-28-2026):** police report, insurer scan, eCW medical export, eCW billing ledger, long scanned Jackman medical bundle, and a working demand draft with attorney flags. See [`docs/example/gold/amini-illustrative.md`](example/gold/amini-illustrative.md).
- **Three additional Jackman demand DOCX files** (other matters): use as **template/style and draft-defect fixtures** (pronouns, incomplete RE blocks, placeholders). They are **not** four complete evidence packages. See [`docs/example/gold/draft-defect-fixtures.md`](example/gold/draft-defect-fixtures.md).

Do not treat an uploaded existing demand as authoritative evidence unless the user explicitly enables it (see FR-CLS-06).

### 3.5 Prototype Operational Limits

The following are configurable starting limits, not permanent product limits:

| Limit | Initial value | Reason |
|-------|---------------|--------|
| Files per session | 20 | Covers representative cases while reducing upload abuse and memory pressure. |
| Pages per session | 300 | Supports a substantial case package on a single-worker prototype. |
| Maximum single file | 75 MB | Limits upload and processing risk on the current connection and machine. |
| Maximum total upload | 250 MB | Protects memory, temporary storage, and processing time. |
| Active OCR workers | 1 | Matches the current hardware and avoids memory contention. |
| Session time-to-live | 2 hours after last activity | Supports temporary runtime processing and automatic cleanup. |

---

## 4. User Roles and Core User Journeys

### 4.1 Primary Roles

| Role | Responsibilities in prototype |
|------|-------------------------------|
| Paralegal | Uploads and organizes documents, reviews facts, corrects data, resolves routine issues, prepares the draft. |
| Attorney | Reviews critical conflicts, approves legal positioning and settlement amount, validates final demand, authorizes export. |
| Prototype administrator/developer | Starts the local service, configures optional LLM provider credentials, monitors processing errors, and manages test settings. |

### 4.2 Primary User Journey

1. Start a new temporary case session.
2. Upload all available documents and select a demand template.
3. Wait while the system validates, extracts, OCRs, classifies, and indexes the documents.
4. Review the proposed document sequence and correct classifications if needed.
5. Review key facts and open each fact at its exact document location.
6. Resolve missing, low-confidence, or conflicting values in the review queue.
7. Review the chronology, medical summary, and billing ledger.
8. Enter user-supplied values that cannot be derived, such as the authorized settlement demand.
9. Generate a demand draft from approved facts.
10. Review the factual-support and preflight report.
11. Resolve remaining blockers and export DOCX.

---

## 5. End-to-End Workflow

```text
NEW SESSION
  → UPLOAD DOCUMENTS
  → VALIDATE + NORMALIZE
  → NATIVE EXTRACTION / OCR
  → DOCUMENT CLASSIFICATION + SEQUENCE
  → SOURCE SPANS + COORDINATES
  → DETERMINISTIC FACTS + CHRONOLOGY + BILLING
  → CONTRADICTIONS + MISSING INFORMATION
  → HUMAN REVIEW / MANUAL COMPLETION
  → APPROVED EVIDENCE SET
  → DEMAND DRAFT GENERATION
  → FACTUAL VERIFICATION + PROGRAMMATIC PREFLIGHT
  → ATTORNEY APPROVAL
  → DOCX EXPORT
```

Optional LLM semantic consolidation may run after deterministic facts when enabled; it is not required for the extraction MVP.

### 5.1 Workflow State Machine

| State | Entry condition | Allowed actions | Exit condition |
|-------|-----------------|-----------------|----------------|
| Created | Session initiated | Upload files; select template | At least one supported document uploaded |
| Ingesting | Files submitted | Cancel; inspect errors | All files validated or rejected |
| Processing | Valid files accepted | View progress; cancel | Extraction and classification complete |
| Reviewing | Facts and issues available | Edit facts; resolve issues; reorder documents | No unresolved blocking issue required for drafting |
| Draftable | Required facts approved | Generate draft | Draft created |
| Draft review | Draft exists | Edit prose; inspect sources; rerun checks | Preflight passes |
| Exportable | All blockers resolved | Export DOCX/PDF | File generated |
| Expired/cleared | TTL, refresh/restart, or user reset | None | Session data deleted |

---

## 6. System Architecture and Technology Stack

### 6.1 Logical Architecture

```text
Browser Application
  ├─ Session state and workflow navigation
  ├─ Upload interface and progress
  ├─ PDF.js document viewer + highlight overlays
  ├─ Fact/issue review editor
  └─ Demand editor and export controls
        │ HTTPS
        ▼
FastAPI Prototype Backend
  ├─ Temporary session manager
  ├─ File validation and conversion
  ├─ Native PDF/DOCX extraction
  ├─ OCR and image preprocessing
  ├─ Deterministic parsers and validators
  ├─ LLM provider adapter (optional / deferred for extraction)
  ├─ Draft generation and verification
  └─ DOCX/PDF export
        │
        ├─ Local OCR models (PaddleOCR)
        └─ Optional external or local LLM API
```

### 6.2 Selected Stack

| Layer | Selected technology | Prototype responsibility |
|-------|---------------------|--------------------------|
| Frontend | React + Vite + TypeScript | Static single-page application and workflow UI. |
| State | Zustand | In-memory case/session state in the browser. |
| Server data fetching | TanStack Query or a lightweight fetch wrapper | Progress polling/SSE, retries, endpoint state. |
| Document viewer | PDF.js | Render pages, navigate, zoom, and display highlights. |
| Rich text editor | TipTap | **Secondary:** editable demand preview after docxtpl export proves the loop. |
| Frontend validation | Zod | Validate API responses and local forms. |
| Backend | Python + FastAPI | Uploads, processing orchestration, optional LLM calls, exports. |
| Backend schemas | Pydantic | Canonical validated contracts and JSON Schema. |
| Native PDF extraction | pdfplumber + pypdf | Text, words, coordinates, pages, metadata, splitting/repair. |
| PDF rendering | **pypdfium2** | Render scan/image pages for OCR — **load-bearing** for the reference corpus. |
| DOCX reading | python-docx | Extract paragraphs/tables and inspect templates. |
| Image preprocessing | Pillow + OpenCV (selective) | Rotate, deskew, denoise, contrast, crop. |
| OCR | **Lightweight PaddleOCR English models** | Printed/scanned text, polygons, confidence — **load-bearing**. |
| LLM | Provider-abstracted structured-output API | Optional: classification fallback, later semantic consolidation, conflicts, drafting, verification, rare vision crop. **Not** primary extraction. |
| DOCX generation | **docxtpl + python-docx** | Populate firm template and apply formatting — **primary** demand deliverable path. |
| PDF preview | LibreOffice headless (optional) | Convert generated DOCX to PDF for preview. |
| Persistence | None beyond active session | Temporary files and in-memory objects only. |

**Template note:** Example firm letters in `docs/example/` are completed or near-completed DOCX demands, not empty Jinja templates. Derive or adapt one firm template (placeholders) from Jackman style for docxtpl.

**Technology Constraint**

Do not use paid document-AI services or large local vision-language document models as the default extractor in the initial prototype. The representative workload does not justify that cost or hardware complexity. Prefer open-source OCR and parsers. Preserve interfaces so a stronger OCR provider can be added later behind the same contracts.

### 6.3 Deployment Profiles

| Profile | Use | Configuration |
|---------|-----|---------------|
| Local development | Developer builds and tests | Frontend and FastAPI on localhost; OCR and export run locally. |
| Lawyer demonstration | One or a few remote testers | Static frontend or local frontend plus secure tunnel to the local FastAPI server; one OCR job at a time. |
| Future hosted pilot | Persistent availability | Replace local server with managed CPU/GPU infrastructure and add proper storage, authentication, tenancy, and compliance controls. |

---

## 7. Core Data Model and Evidence Provenance

> **Field-level contracts:** Entity field tables, enums, and `fact_type` / `issue_type` catalogs live in [`docs/contracts/`](contracts/README.md) (`contracts_version` 0.1). This section remains the conceptual model; implementers should treat `docs/contracts/` as the contracts SoT for shapes.

### 7.1 System of Record

The system of record is the reviewed evidence graph: documents, pages, source spans, extracted facts, user decisions, issues, approved legal clauses, and generated paragraphs. Raw LLM output is never the system of record.

### 7.2 Core Entities

> Conceptual overview only. Machine field shapes: [`docs/contracts/entities/`](contracts/entities/). If this table conflicts with contracts, **contracts win**.

| Entity | Purpose | Key fields |
|--------|---------|------------|
| CaseSession | Temporary workspace | id, created_at, expires_at, status, settings |
| Document | Uploaded original and derived preview | id, filename, type, hash, page_count, classification, status |
| DocumentPage | Page-level extraction and quality | document_id, page_number, width, height, text_coverage, OCR_status, quality flags |
| SourceToken | Smallest positioned text unit | text, confidence, normalized polygon, method |
| SourceSpan | Readable evidence excerpt | text, token_ids, page, polygon(s), context |
| Fact | Normalized case fact | type, value, display_value, confidence, status, source_span_ids |
| Issue | Conflict, uncertainty, or missing information | type, severity, source ids, explanation, resolution |
| TimelineEvent | Chronological event | date/time, event_type, summary, fact_ids |
| BillingEntry | Service or financial line | provider, date, code, charge, payment, adjustment, balance |
| DraftSection | Generated or edited demand section | section_type, text, supporting_fact_ids, verification status |
| UserDecision | Manual intervention record | target id, old value, new value, reason, timestamp |

### 7.3 Coordinate Standard

All source locations must be converted to normalized page coordinates so highlights remain correct at any zoom level. The coordinate origin is the top-left of the displayed page. Store polygons where available; rectangular boxes are acceptable for native words and user-selected regions.

```text
Normalized point:  x = source_x / page_width
                   y = source_y / page_height
Display point:     screen_x = normalized_x × rendered_page_width
                   screen_y = normalized_y × rendered_page_height
```

### 7.4 Example Fact Contract

> **Illustrative only.** Canonical shape: [`docs/contracts/entities/fact.md`](contracts/entities/fact.md).

```json
{
  "id": "fact_01J...",
  "fact_type": "collision.date",
  "raw_value": "03/28/2026",
  "normalized_value": "2026-03-28",
  "display_value": "March 28, 2026",
  "description": "Reported date of the collision.",
  "confidence": 0.99,
  "status": "verified",
  "source_span_ids": ["span_police_p1_18", "span_insurer_p1_09"],
  "extraction_methods": ["regex", "context_parser"],
  "user_override": null
}
```

### 7.5 Fact Statuses

> Canonical enum: [`docs/contracts/enums.md`](contracts/enums.md) (`FactStatus`). Conceptual table below.

| Status | Meaning | Allowed use |
|--------|---------|-------------|
| suggested | Automatically extracted but not yet reviewed | May appear in workspace; not used for final draft when critical |
| verified | High-confidence and consistent, or confirmed by user | May be used for drafting |
| edited | User changed the extracted value | May be used; show edit history |
| conflicting | Sources materially disagree | Cannot be used as settled fact until resolved |
| needs_review | Low confidence or incomplete | May be visible; drafting rule depends on criticality |
| rejected | User or validator determined the fact is wrong/irrelevant | Excluded |
| locked | Attorney-approved fact protected from later automatic replacement | Used as authoritative |

---

## 8. Functional Modules and Requirements

Requirements use the prefix FR. Each module should be implemented behind a defined interface and tested independently.

### 8.1 Session and Workspace

Creates an ephemeral case workspace and controls the workflow state.

**Functional requirements**

- **FR-SES-01** Create a unique opaque session ID and expiration time.
- **FR-SES-02** Store session objects in process memory and temporary files under a session-specific directory.
- **FR-SES-03** Provide Reset Case and Delete Session actions that immediately remove all temporary files and in-memory data.
- **FR-SES-04** Automatically expire inactive sessions and run cleanup even after failed jobs.
- **FR-SES-05** Expose a clear warning that refreshing or losing the session may require starting over.

**Outputs:** Session object; temporary directory; session status and progress channel.

**Module Exit Gate:** A user can start, reset, and expire a case without any residual file remaining in the configured temporary directory.

### 8.2 File Upload, Validation, and Normalization

Accepts supported files, rejects unsafe or unsupported content, and creates canonical working copies.

**Functional requirements**

- **FR-UPL-01** Accept PDF, DOCX, JPG, PNG, and TIFF.
- **FR-UPL-02** Validate extension, MIME type, and file signature; do not trust the filename alone.
- **FR-UPL-03** Generate internal random filenames and retain the original display name only as metadata.
- **FR-UPL-04** Calculate SHA-256 to identify exact duplicates.
- **FR-UPL-05** Reject password-protected, corrupt, unsupported, or oversized documents with specific error messages.
- **FR-UPL-06** Convert DOCX to a canonical PDF viewing copy while retaining structured DOCX extraction.
- **FR-UPL-07** Create page thumbnails and page counts.

**Outputs:** Validated Document records; original temporary files; canonical viewing copies; upload errors/warnings.

**Module Exit Gate:** The supplied sample package uploads successfully, duplicates are detected, and malformed files fail safely without stopping the session.

### 8.3 Page Analysis and Text Extraction

Determines whether each page should use native extraction, OCR, or manual review. For the reference corpus, expect many pages to route to OCR.

**Functional requirements**

- **FR-EXT-01** Extract native words, characters, and coordinates from PDF pages using pdfplumber.
- **FR-EXT-02** Measure native text coverage, character count, replacement-character rate, and reading-order quality.
- **FR-EXT-03** Render pages requiring OCR at a configurable resolution using pypdfium2.
- **FR-EXT-04** Apply rotation and light preprocessing only when page diagnostics indicate a need.
- **FR-EXT-05** Run lightweight PaddleOCR on scanned typed pages and retain polygons and confidence.
- **FR-EXT-06** Produce a single normalized token/span format regardless of extraction method.
- **FR-EXT-07** Create page-level quality warnings for unreadable, blank, duplicate, truncated, or low-confidence pages.

**Outputs:** DocumentPage records; SourceTokens; SourceSpans; page quality flags.

**Module Exit Gate:** Every page in the reference corpus has extractable text or a visible review-queue `Issue`, and clicking an extracted span highlights the correct region.

### 8.4 Document Classification and Sequencing

Labels documents and proposes a logical order for review and generation.

**Functional requirements**

- **FR-CLS-01** Classify using filename, first-page headings, key phrases, page characteristics, and deterministic rules.
- **FR-CLS-02** Call a low-cost LLM classifier only when rule confidence is below threshold (optional if LLM disabled).
- **FR-CLS-03** Support police report, insurer correspondence, medical record, imaging report, bill/ledger, lien, wage loss, photographs, existing demand, template, and other. Imaging may be a section inside a medical bundle rather than a separate file.
- **FR-CLS-04** Extract provider, insurer, claimant, and date-range metadata where applicable.
- **FR-CLS-05** Propose a logical sequence and allow drag-and-drop correction.
- **FR-CLS-06** Prevent an existing demand draft from being treated as authoritative evidence unless the user explicitly enables it as a secondary source.

**Outputs:** Document classification; confidence; reason; proposed sequence.

**Module Exit Gate:** All sample files are correctly classified or surfaced for quick correction, and a user can reorder documents without reprocessing them.

### 8.5 Deterministic Fact Extraction (Extraction MVP)

Extracts common exact values **without using the LLM**. This module, together with OCR/spans and human review, is the **complete extraction MVP**.

**Functional requirements**

- **FR-DET-01** Extract dates, times, dates of birth, phone numbers, email addresses, claim numbers, policy numbers, report numbers, citation numbers, provider names, currency values, CPT codes, and ICD-10 codes.
- **FR-DET-02** Normalize dates, names, currency, identifiers, and codes while preserving raw text.
- **FR-DET-03** Group values by labels and local page context, not regex match alone.
- **FR-DET-04** Assign source spans and confidence to every suggested `Fact`.
- **FR-DET-05** Calculate service ranges, visit counts, and billing totals in code.
- **FR-DET-06** Create Amber/Red `Issue`s for critical fields that fail confidence, format, or cross-source checks rather than guessing.

**Outputs:** Suggested `Fact`s; normalized values; source mappings; deterministic `Issue`s / warnings.

**Module Exit Gate:** Known identity, claim, date, and amount fields from the test corpus are extracted with source links and no invented values. Remaining critical gaps appear in the review queue.

### 8.6 Optional / Deferred — LLM-Assisted Semantic Consolidation

> **Status:** Optional and deferred. **Not required** for the extraction MVP exit gate. Prefer avoiding LLM APIs for data extraction.

Converts selected evidence spans into structured medical, liability, treatment, and damages facts **only when enabled**, and only after deterministic extraction exists.

**Non-goal:** Do not send original full PDFs (or entire page dumps) to an LLM to extract the case.

**Functional requirements (when enabled)**

- **FR-AI-01** Send the model only selected source spans, document metadata, deterministic suggested `Fact`s, and an explicit JSON schema.
- **FR-AI-02** Require every returned fact to cite existing `source_span_ids`.
- **FR-AI-03** Reject or quarantine facts with unknown source IDs, invalid types, or values not represented in the evidence.
- **FR-AI-04** Extract symptoms, diagnoses, examination findings, imaging findings, treatments, medications, referrals, causation opinions, recovery status, restrictions, future care, prior conditions, and daily-life effects.
- **FR-AI-05** Separate observed fact, provider opinion, patient report, legal allegation, and system inference.
- **FR-AI-06** Consolidate duplicates while retaining all supporting and conflicting sources.
- **FR-AI-07** Leave all LLM-proposed semantic facts in `needs_review` or `suggested` until user confirmation for critical categories.

**Outputs:** Structured semantic facts; duplicate groups; evidence classifications.

**Module Exit Gate (when enabled):** The LLM output validates against the schema, every accepted fact has a real source, and unsupported model output is not added to the evidence set.

### 8.7 Chronology and Billing Ledger

Builds structured, verifiable summaries that will later drive the demand. Prefer deterministic dated events and billing rows; do not require LLM extraction to build the ledger.

**Functional requirements**

- **FR-CHR-01** Create collision, treatment, imaging, correspondence, billing, discharge, and settlement events.
- **FR-CHR-02** Sort by normalized date while preserving unknown/approximate dates.
- **FR-CHR-03** Generate provider-specific treatment ranges and visit counts.
- **FR-BIL-01** Extract charge, payment, adjustment, balance, and total lines.
- **FR-BIL-02** Reconcile charge minus payment/adjustment against reported balance.
- **FR-BIL-03** Distinguish amount charged, amount paid, amount outstanding, lien amount, and amount claimed as specials.
- **FR-BIL-04** Require user confirmation when the legally claimed amount is not determinable from the records.

**Outputs:** Chronology; provider treatment summaries; billing entries; reconciliation results.

**Module Exit Gate:** The test case chronology and provider totals match the evidence, and any charge/payment/balance ambiguity is visible rather than silently resolved.

### 8.8 Issue and Contradiction Engine

Detects exact and semantic problems and creates actionable `Issue`s (review queue).

**Functional requirements**

- **FR-ISS-01** Detect exact-value conflicts for identity, dates, claim numbers, policy numbers, provider names, amounts, totals, and treatment ranges (**code first**).
- **FR-ISS-02** Detect missing required documents and facts based on a configurable checklist.
- **FR-ISS-03** Detect placeholders, internal comments, pronoun mismatch, inconsistent party labels, incorrect arithmetic, and exhibit mismatch.
- **FR-ISS-04** After deterministic issues exist, **optionally** use an LLM to propose semantic conflicts (for example fracture versus no fracture, ongoing symptoms versus resolution, pre-existing versus collision-related, or future care versus discharge). Semantic LLM analysis is not required for the extraction MVP.
- **FR-ISS-05** Assign severity, explanation, sources, suggested actions, and whether the issue blocks drafting/export.
- **FR-ISS-06** Never ask the LLM to make the final legal or medical decision; it proposes an issue and options.

**Outputs:** Issue queue; severity and blocking status; suggested resolution options.

**Module Exit Gate:** Known contradictions and drafting defects planted in the sample files are surfaced with correct source links and no silent selection of one source.

### 8.9 Human Review and Manual Intervention

Allows the user to correct extraction failures, decide conflicts, and complete missing values.

**Functional requirements**

- **FR-REV-01** Display Green, Amber, and Red review states.
- **FR-REV-02** Open any fact or issue at its document page and highlighted region.
- **FR-REV-03** Allow Use value, Enter different value, Exclude, Mark unavailable, and Defer to attorney actions.
- **FR-REV-04** Allow the user to draw a rectangle over a document region and create a manual fact source.
- **FR-REV-05** Retain the original extracted value, user value, reason, and source.
- **FR-REV-06** Prevent automatic processes from replacing locked facts.
- **FR-REV-07** After a decision, rerun only affected calculations, summaries, issues, and draft sections.

**Outputs:** Approved facts; resolved issues; user decision log; remaining blockers.

**Module Exit Gate:** A user can resolve an unreadable handwritten value and a semantic contradiction without leaving the workspace, and downstream outputs update correctly.

### 8.10 Demand Generation

Creates a demand draft from approved evidence and firm-controlled template content.

**Functional requirements**

- **FR-DRF-01** Generate only after minimum required facts are present and critical identity/liability conflicts are resolved.
- **FR-DRF-02** Use approved facts and approved clause/template content, not raw full-document text.
- **FR-DRF-03** Require generated paragraphs to return `supporting_fact_ids`.
- **FR-DRF-04** Support header/re line, facts, liability, injuries/treatment by provider, general damages, specials table, settlement proposal, closing, and exhibit list.
- **FR-DRF-05** Allow the user to edit prose while maintaining paragraph-to-fact mapping.
- **FR-DRF-06** Mark edited sentences whose factual support may need re-verification.

**Outputs:** Structured draft sections; paragraph evidence map; editable draft.

**Module Exit Gate:** The draft uses only approved facts, follows the selected template, and every case-specific paragraph can open its evidence.

### 8.11 Verification, Preflight, and Export

Prevents unsupported or defective letters from being exported as final.

**Functional requirements**

- **FR-VAL-01** Programmatically validate names, pronouns, dates, claim/policy numbers, provider names, service ranges, counts, totals, exhibits, and placeholders.
- **FR-VAL-02** Run an independent semantic verifier (when enabled) that labels statements Supported, Partially Supported, Unsupported, Contradicted, Legal Clause, or Argument. Programmatic checks remain the reliable gate even if semantic verification is imperfect.
- **FR-VAL-03** Block final export for unsupported factual statements, unresolved critical issues, invalid calculations, or placeholders.
- **FR-VAL-04** Generate a preflight report and link each finding to the draft and source.
- **FR-EXP-01** Populate the firm DOCX template and export an editable `.docx`.
- **FR-EXP-02** Optionally convert to PDF for preview; the DOCX remains the primary deliverable.

**Outputs:** Verification matrix; preflight report; DOCX export; optional PDF preview.

**Module Exit Gate:** The system refuses to export a draft containing a known placeholder, math error, unsupported factual sentence, or unresolved Red issue.

---

## 9. OCR and Document Processing Strategy

> **Numeric knobs SoT:** Provisional routing/confidence thresholds and `AppSettings` env names live in [`docs/modules/03-ocr-thresholds.md`](modules/03-ocr-thresholds.md). This section remains the strategy narrative.

### 9.1 Routing Decision

For each page:

1. Attempt native extraction.
2. Score native text usability.
3. If usable → keep native text and coordinates.
4. If not usable → render image and run printed-text OCR. **On the reference corpus, this branch is common** (police, insurer scans, long clinical fax stacks).
5. Score OCR coverage and confidence.
6. If uncertain → preprocess and retry once.
7. If still uncertain or handwriting suspected → create an `Issue`.
8. Optionally send only the user-selected/detected crop to a vision-capable LLM (rare; assistive only).
9. User confirms or replaces the value.

### 9.2 Native Text Usability Heuristics

| Signal | Example rule | Interpretation |
|--------|--------------|----------------|
| Character count | Fewer than configurable minimum characters on a visually dense page | Possible scan or extraction failure |
| Replacement characters | High proportion of replacement/control glyphs | Broken encoding |
| Word geometry | Many zero-width/overlapping words | Unusable coordinates |
| Reading order | Line order is severely scrambled | Use blocks/coordinates or OCR |
| Image coverage | Large image area with little text | Likely scanned content |
| Known labels absent | Expected document labels not found | May require OCR or manual review |

### 9.3 OCR Confidence Policy

Do not use one global confidence number as a truth threshold. Combine recognition confidence, source type, agreement with other sources, field criticality, and deterministic validation. A lower-confidence address may be Amber; a lower-confidence date of loss or claim number must be Red.

| Level | Typical condition | System action |
|-------|-------------------|---------------|
| Green | High confidence, valid format, multiple sources agree | Auto-verify or mark review-complete |
| Amber | Moderate confidence, single source, noncritical field | Allow continuation but request confirmation |
| Red | Low confidence, critical field, conflict, illegible handwriting, invalid format | Block dependent workflow until resolved or waived |

### 9.4 Tables and Billing Sheets

For consistent bills and ledgers, use positioned words and row grouping before introducing a table-recognition model. Group words by vertical overlap, assign columns from detected header positions, parse currency with `Decimal`, and verify totals. If the row structure cannot be reconstructed reliably, present the page and extracted line candidates for manual correction. Do not use an LLM as the primary table extractor.

### 9.5 Handwriting

Handwriting is an exception path (~1% of cases; usually 2–3 pages). The printed field label should normally be detected by native extraction or OCR. The handwritten value may be left blank and converted into a targeted review question. The user may enter the value and optionally draw a source rectangle. A vision-capable LLM can be used on the cropped region as an assistive suggestion, but its result must remain unverified until accepted by the user.

---

## 10. LLM Responsibilities and Contracts

### 10.0 Default Policy (v0.2)

**Prefer to avoid LLM APIs for data extraction.**

- **Default on:** OCR, deterministic parsers, cross-document checks, human review.
- **Default off / deferred:** LLM semantic fact extraction from documents.
- **Allowed later, constrained:** classification fallback, semantic issue proposals, drafting from approved facts, independent verification, rare crop transcription.
- **Forbidden as a product pattern:** dumping full case PDFs into an LLM to “extract everything.”

### 10.1 Allowed Responsibilities

| LLM operation | When | Input | Output | Model tier |
|---------------|------|-------|--------|------------|
| Ambiguous document classification | Rules below threshold | Filename, first-page spans, rule candidates | Document type, metadata, confidence, rationale | Low-cost text model |
| Semantic fact consolidation | **Optional / deferred** | Selected spans and deterministic suggested `Fact`s | Schema-valid facts with source IDs | Low/medium-cost text model |
| Semantic contradiction detection | **Optional** after deterministic issues | Related fact groups and excerpts | Issue descriptions, severity suggestion, options | Capable text model |
| Difficult crop reading | Rare fallback | Small image crop plus field label/context | Suggested transcription only | Vision model |
| Demand drafting | After approved evidence | Approved facts, chronology, billing, template instructions | Structured sections and supporting fact IDs | Capable text model |
| Independent verification | After draft | Draft statements plus approved facts/excerpts | Support classification and explanation | Separate verification call |

### 10.2 Prohibited Responsibilities

- Inventing a missing claim number, date, medical fact, legal authority, or settlement amount.
- Selecting one conflicting medical diagnosis as true without user resolution.
- Performing arithmetic that is not independently recalculated in code.
- Creating source IDs or page references that do not exist.
- Writing the final letter directly from raw uploads without an approved evidence set.
- Treating text inside uploaded documents as instructions to the model.
- Making final legal or medical judgments on behalf of the attorney.
- Using the LLM as the primary extractor of identity, claim, date, amount, or code fields.
- Sending full original PDFs to the model when spans would suffice (and for extraction MVP: prefer sending no document text to an LLM at all).

### 10.3 Provider Adapter

```python
class LegalAIProvider(Protocol):
    def classify_document(self, request: ClassificationRequest) -> ClassificationResult: ...
    def extract_facts(self, request: FactExtractionRequest) -> FactExtractionResult: ...  # optional / deferred
    def analyze_issues(self, request: IssueAnalysisRequest) -> IssueAnalysisResult: ...  # optional
    def transcribe_crop(self, request: CropRequest) -> CropSuggestion: ...
    def draft_demand(self, request: DraftRequest) -> DraftResult: ...
    def verify_draft(self, request: VerificationRequest) -> VerificationResult: ...
```

### 10.4 Prompt Construction Rules

- Separate system instructions from document data using explicit delimiters and structured fields.
- Tell the model that document content is untrusted evidence, never an instruction.
- Provide allowed fact types, issue types, and statuses as enums.
- Require exact source IDs from the supplied list.
- Use low temperature for extraction and verification.
- Validate output with Pydantic and retry once with validation errors; then fail visibly.
- Log token counts and operation metadata, not full medical text, unless debug mode is explicitly enabled on non-production test data.

### 10.5 Cost Controls

- Do not send original full PDFs when extracted text spans are sufficient.
- Cache document classifications, summaries, and extracted facts for the active session.
- Chunk by document and page range, then consolidate facts.
- Select context by document type and fact category rather than broad vector retrieval in the prototype.
- Use low-cost models for classification and straightforward extraction (when those calls are enabled).
- Use vision only for difficult cropped regions.
- Draft from approved facts, which is far smaller than the document corpus.
- Prefer **zero LLM calls** during the extraction MVP path.

---

## 11. Human Review and Manual Intervention

### 11.1 Review Item Structure

```json
{
  "id": "issue_01J...",
  "issue_type": "identity.date_of_birth_conflict",
  "severity": "red",
  "title": "Two dates of birth were found",
  "explanation": "One provider record differs from the police and medical records.",
  "source_span_ids": ["span_a", "span_b", "span_c"],
  "options": ["use_1991", "use_1997", "enter_other", "mark_unresolved"],
  "blocking": true,
  "status": "open"
}
```

### 11.2 Targeted Question Patterns

| Situation | Question shown to user | Available actions |
|-----------|------------------------|-------------------|
| Unreadable field | The policy number on page 6 could not be read reliably. What value should be used? | Open source; enter value; mark unavailable |
| Exact conflict | The police report says March 28; a provider note says March 20. Which date is authoritative? | Choose source; enter value; add explanation |
| Medical conflict | A chiropractic record references a fracture, while a later MRI does not. How should the demand address this? | Exclude; qualify; attorney review; add note |
| Missing evidence | The insurer requested final liens, but no final lien document was found. | Upload document; mark unavailable; continue with warning |
| User-supplied decision | No authorized settlement amount can be derived from the records. | Enter amount; leave blank; block drafting |

### 11.3 Reprocessing After Intervention

A user change should invalidate only dependent outputs. For example, changing the date of loss should rerun date-conflict rules, chronology labels, letter header fields, and affected draft sentences. It should not repeat OCR for unrelated pages.

---

## 12. Demand Letter Generation and Validation

### 12.1 Draft Input Package

- Approved identity, claim, collision, liability, medical, damages, and correspondence facts.
- Approved chronology and provider treatment summaries.
- Reconciled billing ledger and user-confirmed medical specials.
- Resolved issue decisions and qualifications that must appear in the letter.
- Firm template, tone, headings, approved legal clauses, and exhibit rules.
- User-supplied demand amount and offer deadline.

### 12.2 Draft Section Contract

```json
{
  "section_type": "treatment_summary",
  "heading": "SUMMARY OF INJURIES AND TREATMENT",
  "paragraphs": [
    {
      "text": "...",
      "supporting_fact_ids": ["fact_102", "fact_118"],
      "contains_argument": false
    }
  ]
}
```

### 12.3 Programmatic Preflight Rules

| Category | Checks |
|----------|--------|
| Identity | Client, insured, adjuster, insurer, gender/pronouns, DOB, address where used |
| Claim | Claim number, policy number, date/location of loss, report/citation number |
| Medical | Provider names, treatment ranges, visit counts, diagnosis wording, recovery status |
| Billing | Totals, charge/payment/balance, provider subtotal, specials total, multiplier display if used |
| Draft hygiene | No TBD, bracketed notes, attorney flags, comments, duplicate paragraphs, inconsistent headings |
| Exhibits | Every listed exhibit exists; no uploaded exhibit is unintentionally omitted |
| Support | All factual sentences have approved facts; no contradicted fact is presented as settled |
| User decisions | Demand amount and expiry are present; all Red issues resolved or explicitly waived |

### 12.4 Export Policy

Provide Draft Export only when noncritical warnings remain. Label it clearly as a draft. Provide Final Export only after all blocking checks pass and the attorney confirms approval. Embed no hidden prompts, source IDs, or review notes in the final visible document. Keep an internal session copy of the paragraph-to-fact map until session cleanup.

---

## 13. User Interface Specification

> **SoT split:** This section is the **product narrative** for the workspace. Implementers follow [`docs/modules/ui-notes.md`](modules/ui-notes.md) for panel/recovery UX detail, [`docs/contracts/error-codes.md`](contracts/error-codes.md) for user-facing messages (codes win), and the [Phase ↔ Module ↔ UI crosswalk](modules/README.md#phase--module--ui-crosswalk) for step ↔ module mapping.

### 13.1 Main Workspace Layout

```text
┌──────────────────┬───────────────────────────┬───────────────────────────┐
│ DOCUMENTS        │ FACTS / TIMELINE / ISSUES │ SOURCE VIEWER             │
│                  │                           │                           │
│ Police Report    │ Date of loss              │ PDF.js page               │
│ Medical Records  │ Liability                 │ Highlighted source span   │
│ Bills            │ Treatment chronology      │ Context around evidence   │
│ Insurance        │ Billing                   │                           │
│ Template         │ Review queue              │                           │
└──────────────────┴───────────────────────────┴───────────────────────────┘
```

### 13.2 Primary Navigation

| Step | Screen | Purpose |
|------|--------|---------|
| 1 | Documents | Upload, processing progress, classification, sequence, page quality. |
| 2 | Facts | Review identity, claim, liability, medical, and damages facts. |
| 3 | Timeline & Billing | Review chronological events, treatment ranges, bills, totals, and reconciliation. |
| 4 | Issues | Resolve Red/Amber concerns and missing information. |
| 5 | Demand | Generate, edit, and inspect source support. |
| 6 | Preflight | Review validation results and export. |

### 13.3 Document Panel

- Show icon, filename, classification, page count, processing status, and warning count.
- Allow rename of display label, classification correction, sequence change, and exclusion from drafting.
- Show whether the file is native text, scanned, mixed, or contains review-required pages.
- Provide page thumbnails and quick navigation to pages with facts or issues.

### 13.4 Fact Panel

- Group facts by category and show status, value, confidence, source count, and conflict count.
- Clicking a fact opens its primary source and allows switching among supporting sources.
- Editing requires a value and optional reason; locking is available after attorney approval.
- Show whether a value was extracted, calculated, inferred, or user-supplied.

### 13.5 Issue Panel

- Sort by severity, category, blocker status, and document.
- Show a concise title first, followed by explanation, source evidence, and recommended actions.
- Provide side-by-side source comparison for conflicting facts.
- After resolution, display the selected decision and any required qualification for the letter.

### 13.6 Source Viewer

- Use PDF.js for the canonical page view.
- Support zoom, page navigation, thumbnails, and exact highlight overlays.
- Highlight all polygons associated with the selected fact or sentence.
- Show the extracted text, extraction method, and confidence beside the page.
- Allow the user to drag a rectangle and create a manual source span.

### 13.7 Demand Editor

- Prefer **docxtpl-generated DOCX download** as the first complete drafting deliverable.
- TipTap (or equivalent) in-app editing is secondary and may follow once paragraph-to-fact mapping is proven.
- Display sections in the firm’s preferred order.
- Show support status at paragraph or sentence level.
- Clicking a supported sentence opens the associated facts and source documents.
- Edited factual sentences become “verification required” until rechecked.
- Template-controlled legal clauses should be visually distinguishable from generated case narrative in review mode, but not in the exported document.

### 13.8 Error and Recovery States

> **Detail SoT:** Machine codes and messages — [`docs/contracts/error-codes.md`](contracts/error-codes.md) (**codes win**). Panel/recovery UX — [`docs/modules/ui-notes.md`](modules/ui-notes.md). Do not maintain a second copy of user messages in this section.

| Condition | Recovery (summary) | Authoritative `error_code` |
|-----------|--------------------|----------------------------|
| Unsupported file | Remove or convert file | `upload_unsupported_type` |
| Encrypted PDF | Provide an unlocked copy | `upload_encrypted_pdf` |
| Extraction failure | Open pages / Issues; enter values manually | page quality → `Issue`s |
| LLM schema failure | Retry once; preserve prior evidence; show `request_id` | `draft_llm_schema_failed` |
| Session expiry | Start a new case | `session_expired` |
| Export blocker | Open blocking issues / Preflight | `export_blocked_*` |

---

## 14. API and Backend Contract

### 14.1 API Principles

- Use versioned routes under `/api/v1`.
- Return Pydantic-validated JSON for all non-file responses.
- Use opaque UUID/ULID identifiers; never expose local file paths.
- Use idempotency keys for processing and generation requests where practical.
- Use server-sent events or polling for long-running progress; one worker processes heavy jobs sequentially.
- Return machine-readable error codes plus user-facing messages.

### 14.2 Proposed Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/sessions` | Create temporary case session. |
| DELETE | `/api/v1/sessions/{session_id}` | Delete session and temporary data. |
| POST | `/api/v1/sessions/{session_id}/documents` | Upload one or more documents. |
| GET | `/api/v1/sessions/{session_id}/documents` | List documents and processing status. |
| POST | `/api/v1/sessions/{session_id}/process` | Start validation, extraction, OCR, classification, facts, and issues. |
| GET | `/api/v1/sessions/{session_id}/events` | Stream or poll progress events. |
| PATCH | `/api/v1/sessions/{session_id}/documents/{document_id}` | Correct classification, label, sequence, or exclusion. |
| GET | `/api/v1/sessions/{session_id}/facts` | Return grouped facts. |
| PATCH | `/api/v1/sessions/{session_id}/facts/{fact_id}` | Verify, edit, lock, or reject fact. |
| POST | `/api/v1/sessions/{session_id}/source-spans/manual` | Create user-selected source region. |
| GET | `/api/v1/sessions/{session_id}/issues` | Return review queue. |
| POST | `/api/v1/sessions/{session_id}/issues/{issue_id}/resolve` | Record resolution or waiver. |
| GET | `/api/v1/sessions/{session_id}/timeline` | Return chronology. |
| GET | `/api/v1/sessions/{session_id}/billing` | Return ledger and reconciliation. |
| POST | `/api/v1/sessions/{session_id}/drafts` | Generate a demand draft. |
| PATCH | `/api/v1/sessions/{session_id}/drafts/{draft_id}` | Save user edits to structured draft. |
| POST | `/api/v1/sessions/{session_id}/drafts/{draft_id}/verify` | Run semantic verification and preflight. |
| POST | `/api/v1/sessions/{session_id}/exports` | Generate DOCX and optional PDF. |
| GET | `/api/v1/sessions/{session_id}/exports/{export_id}` | Download generated file. |

### 14.3 Processing Job Stages

```text
queued
  → validating
  → normalizing
  → extracting_native
  → rendering_pages
  → ocr
  → classifying
  → extracting_deterministic
  → extracting_semantic      # optional / skippable when LLM extraction disabled
  → building_timeline
  → building_billing
  → analyzing_issues
  → completed
```

### 14.4 Progress Event Contract

```json
{
  "event": "document.page.processed",
  "session_id": "ses_...",
  "document_id": "doc_...",
  "page_number": 17,
  "stage": "ocr",
  "percent": 63,
  "message": "Processed page 17 of 24",
  "warnings": []
}
```

### 14.5 Internal Service Interfaces

| Service | Interface responsibility |
|---------|--------------------------|
| SessionService | Lifecycle, TTL, cleanup, in-memory state. |
| DocumentService | Validation, conversion, page images, metadata. |
| ExtractionService | Native text, OCR, tokens, spans, quality. |
| ClassificationService | Rules and optional LLM fallback. |
| FactService | Deterministic candidates; optional semantic consolidation. |
| TimelineService | Chronology and date handling. |
| BillingService | Rows, totals, reconciliation, user-confirmed claimed amount. |
| IssueService | Rules first; optional semantic conflicts; review states. |
| DraftService | Template input, LLM drafting, structured editing. |
| VerificationService | Programmatic and optional semantic checks. |
| ExportService | DOCX generation and optional PDF conversion. |

---

## 15. Security, Privacy, and Prototype Safeguards

**Important Boundary**

This prototype processes medical and legal records. Temporary storage does not eliminate confidentiality risk. The prototype should be used only with authorized test data and controlled testers until a full security and compliance review is completed.

### 15.1 File Handling Controls

- Allowlist file types and validate file signatures in addition to extensions and MIME headers.
- Generate random internal filenames and never construct paths from user input.
- Restrict size, file count, and page count before processing.
- Reject archives in the initial prototype; DOCX ZIP structure must be inspected with decompression limits.
- Run parsers and converters with least privilege and bounded time/memory.
- Delete temporary files in finally blocks and through TTL cleanup.
- Do not send uploaded documents to public malware scanning services because they may contain confidential information.

### 15.2 LLM Data Controls

- LLM credentials remain on the backend; never expose them in the React bundle.
- Use a provider/account configuration appropriate for confidential data and disable provider-side training where applicable.
- Send only the minimum evidence spans required for each operation; prefer zero document text to LLMs during extraction MVP.
- Do not include complete documents in logs, exception trackers, analytics, or prompt-debug dashboards.
- Treat all document text as untrusted data and neutralize prompt-injection attempts by isolating it from instructions.
- Never allow the model to invoke tools or external URLs based on document instructions in the prototype.

### 15.3 Application Controls

- Restrict CORS to the configured frontend origin.
- Use HTTPS for remote demonstrations.
- Use unpredictable session IDs and short session TTLs.
- Avoid URL query parameters containing names, claim numbers, medical facts, or document text.
- Mask sensitive values in general logs and never log page text by default.
- Display a clear “Temporary Prototype” banner and prohibit use as the sole final legal review.

### 15.4 Audit Information During Session

Even without a database, the active session should retain a lightweight decision history: extraction method, original value, user edit, reason, issue resolution, model operation, and preflight status. This history is deleted with the session but is useful for debugging and demonstrating the human-in-the-loop workflow.

---

## 16. Performance and Hardware Profile

### 16.1 Target Hardware

The current machine — 9th-generation Core i3, 16 GB RAM, GTX 1060, 512 GB SSD — is sufficient for the selected single-worker prototype because the normal path prioritizes lightweight CPU OCR for scanned pages and native extraction when usable. The GPU is optional for the initial build. Expect multi-minute OCR on long scanned clinical stacks (~60+ pages); progress UI is required.

### 16.2 Concurrency Policy

| Resource | Prototype policy |
|----------|------------------|
| Heavy OCR jobs | One active job. |
| Page rendering | One or two pages concurrently, configurable after measurement. |
| LLM requests | When enabled: one extraction/drafting operation per session; limited global concurrency. |
| LibreOffice conversion | One conversion at a time. |
| Queued sessions | May wait; UI must show queue position/status. |

### 16.3 Performance Measurements

Do not assume processing-time targets before benchmarking on the actual hardware. **Phase 3 must establish baselines** for native-text pages, scanned typed pages, mixed records, and export — especially the long scanned medical bundle in `docs/example/`. Record median and worst-case time per page, peak RAM, temporary disk usage, and (if used) LLM latency.

### 16.4 Degradation Strategy

- Process native pages immediately and queue OCR pages.
- Render at lower DPI first; retry selected pages at higher DPI.
- Avoid loading optional models until required.
- Pause new OCR work during DOCX/PDF conversion if memory is constrained.
- Allow the user to skip an unreadable nonessential page or mark it for manual review.

---

## 17. Testing, Evaluation, and Human Baseline Comparison

### 17.0 Extraction Accuracy Definition

For evaluation, treat a critical field as correct only if:

1. The normalized value matches the gold answer key, **and** a clickable source span opens the right page/region; **or**
2. The system left the field Amber/Red with a clear review-queue `Issue` (no silent wrong value).

Do not use “LLM extracted a plausible narrative” as an extraction success metric.

### 17.1 Test Strategy

| Level | Focus | Examples |
|-------|-------|----------|
| Unit | Pure functions and parsers | Date normalization, money parsing, coordinate conversion, totals, status transitions. |
| Component | Individual services | PDF extraction, OCR adapter, document classifier, fact consolidator. |
| Contract | Schemas and (optional) LLM outputs | Reject unknown source IDs, invalid enums, malformed JSON, unsupported values. |
| Integration | Multi-service workflows | Upload to facts; issue resolution to updated draft; draft to DOCX. |
| Golden corpus | Known expected results | `docs/example/` Amini package with lawyer-approved facts and issues; other DOCX demands as defect fixtures. |
| Usability | Lawyer/paralegal review speed | Can a user understand and resolve each issue without developer assistance? |
| Security | Upload and prompt handling | Invalid signatures, oversized files, path names, prompt-injection text, cleanup. |

### 17.2 Gold-Standard Dataset

Create a lawyer-approved answer key for each test case. It should include authoritative identity and claim facts, liability facts, treatment chronology, diagnoses and findings, provider totals, known contradictions, required exhibits, and an approved demand draft or section-level expected content. The answer key must distinguish objective facts from attorney judgment.

Primary gold path: **Amini evidence PDFs** (do not feed the Amini demand into the drafting pipeline as authority unless testing FR-CLS-06). Secondary fixtures: Ahmed / Morris / Fuentes DOCX for pronoun, RE/salutation, and placeholder defects.

### 17.3 Evaluation Metrics

| Metric | Definition | Desired direction |
|--------|------------|-------------------|
| Document classification accuracy | Correct document type and provider/insurer metadata | Higher |
| Key fact precision | Accepted extracted facts that are correct | Higher |
| Key fact recall | Gold facts successfully found | Higher |
| Silent critical-error rate | Wrong critical field accepted without review | Zero target |
| Source-link accuracy | Facts that open the correct document/page/region | Higher |
| Contradiction recall | Known material conflicts detected | Higher |
| False issue rate | Issues that are not meaningful or are duplicates | Lower |
| Billing accuracy | Correct entries, subtotals, and reconciliation | Higher |
| Unsupported statement rate | Draft factual statements without adequate evidence | Zero target |
| Human corrections | Number and significance of required corrections | Lower |
| Time to reviewed first draft | Upload to user-reviewed draft | Lower |
| Attorney revision time | Time needed after system draft | Lower |

### 17.4 Demonstrating “Better Than the Current Process”

1. Select several representative completed cases with permission to use them for evaluation.
2. Create a lawyer-approved gold fact set and issue list.
3. Record the time and errors for the current workflow: manual review plus ChatGPT/Claude prompting.
4. Run the prototype on the same files without revealing the existing final demand to the drafting pipeline.
5. Blind-review the two drafts for accuracy, completeness, clarity, chronology, unsupported statements, and revision effort.
6. Report results by task rather than making a broad unsupported claim that the system is universally better than humans.

### 17.5 Minimum Prototype Acceptance Criteria

| Area | Acceptance criterion |
|------|----------------------|
| Traceability | Every accepted critical fact has at least one source span; at least one click opens the correct page and visible region. |
| No silent failures | Every unprocessed or low-confidence page is visible in the review queue. |
| Extraction MVP | Critical exact facts from the Amini gold set are present or queued without LLM extraction. |
| Contradictions | All deliberately seeded identity, date, diagnosis, billing, placeholder, and pronoun issues in the reference set are detected. |
| Calculations | All arithmetic and visit counts match deterministic test fixtures. |
| Draft support | No final-export factual sentence is classified as unsupported or contradicted. |
| Human review | A nontechnical legal user can resolve the test review queue without editing JSON or using developer tools. |
| Export | Generated DOCX opens correctly in Word/LibreOffice and preserves the selected template structure. |
| Cleanup | Session deletion removes temporary files and in-memory state. |

---

## 18. Modular Implementation Roadmap

The roadmap is intentionally sequential. Each phase should produce a working, testable increment rather than a partially connected set of features.

### Phase 0 — Repository and Contracts

Establish project structure, schemas, coding standards, test harness, and sample fixtures.

**Deliverables:** Frontend/backend repositories or monorepo; Pydantic and TypeScript entity schemas implemented from [`docs/contracts/`](contracts/README.md); configuration system; test runner and CI; dependency/license inventory.

**Exit Gate:** Schemas compile, frontend and backend exchange a validated health payload, and tests run with one command.

### Phase 1 — Temporary Session and Upload

Create/reset sessions, upload files, validate types/limits, hash, and clean up.

**Deliverables:** Session manager; upload UI; validation errors; temporary directory lifecycle; document list.

**Exit Gate:** Reference files upload and cleanup is verified; no OCR or AI yet.

### Phase 2 — Canonical Viewer and Native Extraction

Render PDFs, convert DOCX to viewing copies, extract native text and coordinates.

**Deliverables:** PDF.js viewer; page thumbnails; pdfplumber extraction; source token/span model; click-to-highlight test.

**Exit Gate:** A selected native fact opens the exact source location (where native text exists).

### Phase 3 — OCR Fallback and Page Quality (**critical path for demos**)

Add page routing, image rendering, lightweight OCR, confidence, and manual page warnings. Required for a credible Amini demo because much of the reference package is scanned.

**Deliverables:** pypdfium2 renderer; PaddleOCR adapter; OpenCV retry path; page quality dashboard; hardware benchmark on the long scanned medical bundle.

**Exit Gate:** All reference pages are either extracted or explicitly flagged; baseline speed and memory are documented.

### Phase 4 — Document Classification and Sequence

Classify documents using rules first and optional LLM fallback second.

**Deliverables:** Document taxonomy; rule engine; optional LLM classification contract; sequence UI; correction workflow.

**Exit Gate:** Reference documents are classified or corrected in seconds without reprocessing.

### Phase 5 — Deterministic Facts and Evidence (**extraction MVP without LLM**)

Extract identity, claim, dates, identifiers, amounts, codes, and source links. With Phases 2–4 and human review affordances, this phase completes a usable **extraction MVP** — no LLM required.

**Deliverables:** Regex/context parsers; normalization; fact browser; fact source navigation; duplicate/conflict candidates; Amber/Red queue for critical gaps.

**Exit Gate:** Critical exact facts from the gold set are present and traceable, or explicitly queued. Silent inventing is absent.

### Phase 6 — Timeline, Billing, and Optional Semantic Consolidation

Build chronology, provider summaries, billing rows, and reconciliation from deterministic facts. **Optional:** enable constrained LLM semantic consolidation on selected spans (deferred if extraction quality is already adequate).

**Deliverables:** Timeline view; billing ledger; arithmetic tests; optional fact-extraction prompts/schemas.

**Exit Gate:** The reference chronology and billing totals match the gold set or create review-queue `Issue`s. LLM path is skippable.

### Phase 7 — Issue Engine and Human Review

Detect exact issues in code first; optional semantic issue prompts later. Implement manual intervention.

**Deliverables:** Issue rules; optional semantic issue prompt; Green/Amber/Red queue; side-by-side evidence; manual rectangle/source entry; decision log.

**Exit Gate:** Known sample contradictions are detected and resolvable; downstream data updates.

### Phase 8 — Demand Generation

Generate structured sections from approved evidence and selected template.

**Deliverables:** Template manager (derived from firm DOCX style); draft request contract; structured section output; **docxtpl DOCX export first**; TipTap editor as a later polish; paragraph-to-fact map.

**Exit Gate:** A complete demand draft is generated without raw-document prompting; editable DOCX opens in Word.

### Phase 9 — Verification and Export

Add deterministic preflight, optional independent verifier, DOCX generation hardening, and optional PDF preview.

**Deliverables:** Preflight engine; statement support matrix; export blocker rules; docxtpl/python-docx output; rendering QA.

**Exit Gate:** The system blocks seeded defects and exports a clean editable DOCX after resolution.

### Phase 10 — Evaluation Demonstration

Measure the prototype against the current lawyer workflow.

**Deliverables:** Gold corpus runner; metric collection; timing dashboard/report; blind review packet; demonstration script. Module design: [`docs/modules/12-evaluation-demonstration.md`](modules/12-evaluation-demonstration.md). Gold **shape** remains under [`docs/example/gold/`](example/gold/README.md).

**Exit Gate:** Results are repeatable and show where the prototype is faster, more traceable, or less error-prone.

### 18.1 Recommended Build Order Within Each Phase

1. Define the schema and test fixture.
2. Implement deterministic core logic.
3. Add the API contract.
4. Add the UI state and user interaction.
5. Add LLM integration only where the deterministic path is insufficient **and** the feature is explicitly in scope for that phase.
6. Run unit, integration, and reference-corpus tests.
7. Document known limitations before moving forward.

**Numbering map:** Roadmap Phase ≠ Module file number ≠ UI step. Use the single crosswalk in [`docs/modules/README.md`](modules/README.md#phase--module--ui-crosswalk) (e.g. Module 10 = Phase 9 Preflight/Export; Module 12 = Phase 10 Evaluation; Module 02 shares Phase 1 with Module 01).

---

## 19. Risks, Limitations, and Future Expansion

### 19.1 Key Prototype Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| OCR misreads critical identifiers | Wrong claim/date/name enters workflow | Criticality-aware review; cross-source checks; manual confirmation. |
| LLM invents or overstates facts | Inaccurate demand narrative | Prefer no LLM in extraction; source-ID constraints; schema validation; independent verification; export blockers. |
| Medical nuance is oversimplified | Misleading treatment or causation summary | Separate patient report/provider opinion/objective finding; attorney review. |
| Template variation | Poor output formatting or missing sections | Start with one firm template derived from Jackman style; add template profiles later. |
| Long scanned files overload current hardware | Slow or failed jobs | One worker; page routing; limits; selective OCR; progress and retry. |
| Temporary session loss | User must restart | Clear warning; optional future encrypted autosave after prototype. |
| Confidentiality exposure | Client harm and ethical risk | Controlled testers, minimum external data, secure tunnel/HTTPS, no content logs. |
| User trusts automation too much | Insufficient legal review | Mandatory review states, attorney approval, product disclaimers, blockers. |

### 19.2 Future Expansion After Prototype Validation

- Persistent encrypted case storage and resumable sessions.
- Firm accounts, role-based access, matter permissions, and full audit history.
- Template and clause library by jurisdiction and practice area.
- Additional demand types, including premises liability and other personal-injury matters.
- Managed OCR/document-intelligence fallback for hard cases (still behind the same interfaces).
- Background job queue, multiple workers, and hosted infrastructure.
- Email ingestion, exhibit packet assembly, and insurer correspondence tracking.
- Search across cases, analytics, and firm-specific learned extraction rules.
- Formal security, privacy, retention, and compliance programme.
- Optional constrained LLM semantic consolidation once the deterministic evidence path is proven.

---

## Appendix A — Canonical Fact Taxonomy

> **Machine codes SoT:** dotted `fact_type` values in [`docs/contracts/fact-types.md`](contracts/fact-types.md). This appendix is a domain overview; do not implement undotted labels as API codes.

| Domain | Examples |
|--------|----------|
| Identity | client.name, client.dob, client.address, client.pronouns, attorney.name |
| Claim | insurer.name, insured.name, adjuster.name, claim.number, policy.number |
| Collision | collision.date, time, location, vehicles, impact type, airbags, transport |
| Liability | traffic signal, admissions, citation, police finding, witness, comparative-fault allegation |
| Medical encounter | provider, visit date, complaint, pain score, exam finding, diagnosis, treatment, medication |
| Imaging | study date, modality, level, finding, measurement, stenosis, fracture, recommendation |
| Recovery | improvement, resolved symptoms, discharge, MMI, restrictions, future care |
| Prior condition | pre-existing diagnosis, prior symptoms, asymptomatic status, aggravation opinion |
| Damages | charge, payment, adjustment, balance, lien, wage loss, out-of-pocket expense |
| Correspondence | requested items, response deadline, offer deadline, missing document |
| Demand parameters | authorized amount, multiplier if firm uses one, offer expiry, exhibit order |

---

## Appendix B — Issue Taxonomy

> **Machine codes SoT:** dotted `issue_type` values in [`docs/contracts/issue-types.md`](contracts/issue-types.md) (e.g. `extraction.unreadable_page`). This appendix lists short names for readability only.

| Category | Issue types |
|----------|-------------|
| Extraction | unreadable_page, low_ocr_confidence, broken_text_layer, truncated_text, suspected_handwriting |
| Identity | name_conflict, dob_conflict, pronoun_conflict, address_conflict |
| Claim | claim_number_conflict, policy_number_conflict, insurer_conflict |
| Collision | date_of_loss_conflict, location_conflict, liability_narrative_conflict |
| Medical | diagnosis_conflict, fracture_conflict, symptom_status_conflict, prior_condition_conflict, future_care_conflict |
| Billing | unreconciled_balance, duplicate_charge, total_mismatch, missing_bill, missing_lien |
| Draft | placeholder, internal_note, unsupported_statement, contradicted_statement, pronoun_mismatch, duplicate_section |
| Exhibits | listed_missing, uploaded_unlisted, wrong_numbering |
| User input | missing_demand_amount, missing_deadline, unresolved_attorney_decision |

---

## Appendix C — Suggested Repository Structure

```text
prototype/
  frontend/
    src/
      app/
      components/
      features/documents/
      features/facts/
      features/issues/
      features/draft/
      viewer/
      schemas/
      store/
  backend/
    app/
      api/v1/
      core/
      models/
      services/session/
      services/documents/
      services/extraction/
      services/ocr/
      services/classification/
      services/facts/
      services/timeline/
      services/billing/
      services/issues/
      services/llm/
      services/drafting/
      services/verification/
      services/export/
    tests/
      unit/
      integration/
      golden/
  templates/
  fixtures/
  docs/
  scripts/
```

---

## Appendix D — Prototype Configuration Defaults

> Defaults also live on [`docs/contracts/entities/app-settings.md`](contracts/entities/app-settings.md). OCR routing knobs: [`docs/modules/03-ocr-thresholds.md`](modules/03-ocr-thresholds.md). If values diverge, prefer the contracts entity + thresholds addendum after calibration.

```text
SESSION_TTL_MINUTES=120
MAX_FILES_PER_SESSION=20
MAX_PAGES_PER_SESSION=300
MAX_FILE_SIZE_MB=75
MAX_TOTAL_UPLOAD_MB=250
OCR_WORKERS=1
OCR_RENDER_DPI=200
OCR_RETRY_DPI=300
NATIVE_MIN_CHARS=40
NATIVE_MIN_TEXT_COVERAGE=0.02
NATIVE_MAX_REPLACEMENT_RATIO=0.05
NATIVE_MAX_ZERO_WIDTH_OR_OVERLAP_RATIO=0.15
NATIVE_MIN_READING_ORDER_SCORE=0.55
NATIVE_LIKELY_SCAN_IMAGE_COVERAGE=0.60
OCR_PAGE_MEAN_CONF_LOW=0.55
OCR_PAGE_MEAN_CONF_RETRY_TRIGGER=0.70
ENABLE_LLM_SEMANTIC_EXTRACTION=false
LLM_EXTRACTION_TEMPERATURE=0
LLM_DRAFT_TEMPERATURE=0.2
ALLOW_VISION_CROP_FALLBACK=true
ALLOW_FINAL_EXPORT_WITH_RED_ISSUES=false
LOG_DOCUMENT_TEXT=false
```

See also [`docs/modules/03-ocr-thresholds.md`](modules/03-ocr-thresholds.md) for policy matrices (`thresholds_version` `0.1-provisional`).

---

## Appendix E — Definition of Done Checklist

- [ ] A representative case package can be uploaded and processed end to end.
- [ ] Every page is classified as native, OCR, or manual review.
- [ ] Documents are classified and can be reordered.
- [ ] Key facts are normalized and linked to exact source locations **without requiring LLM extraction**.
- [ ] Critical gaps appear as Amber/Red `Issue`s (review queue) rather than silent values.
- [ ] Known contradictions are visible and resolvable.
- [ ] Handwritten uncertainty can be completed manually with a selected source region.
- [ ] Chronology and billing totals are reproducible from evidence.
- [ ] Demand generation uses approved facts only.
- [ ] Every generated factual paragraph has supporting fact IDs.
- [ ] Preflight detects placeholders, arithmetic defects, unsupported statements, and missing exhibits.
- [ ] Final export is blocked until critical issues are resolved.
- [ ] The DOCX opens cleanly and follows the template.
- [ ] Temporary files are deleted at reset/expiry.
- [ ] Evaluation metrics can be collected for comparison with the current workflow.

---

## Appendix F — Research and Engineering References

The following primary sources informed the technology and risk-control decisions in this specification:

1. Mozilla PDF.js API — PDFPageProxy.getTextContent and page viewport: https://mozilla.github.io/pdf.js/api/draft/module-pdfjsLib-PDFPageProxy.html
2. Mozilla PDF.js examples — browser PDF parsing and rendering: https://mozilla.github.io/pdf.js/examples/
3. pdfplumber project documentation — detailed PDF objects, text, tables, and bounding boxes: https://github.com/jsvine/pdfplumber
4. PaddleOCR general OCR pipeline documentation: https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/pipeline_usage/OCR.html
5. PaddleOCR text detection documentation — bounding boxes for text regions: https://paddlepaddle.github.io/PaddleOCR/main/en/version3.x/module_usage/text_detection.html
6. FastAPI request file documentation — UploadFile and multipart uploads: https://fastapi.tiangolo.com/tutorial/request-files/
7. Pydantic documentation — validation and JSON Schema configuration: https://docs.pydantic.dev/2.11/api/config/
8. OWASP File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
9. OWASP LLM Prompt Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
10. NIST AI Risk Management Framework and human-AI interaction guidance: https://www.nist.gov/itl/ai-risk-management-framework
11. NIST AI RMF: AI risks and trustworthiness — human intervention when systems cannot correct errors: https://airc.nist.gov/airmf-resources/airmf/3-sec-characteristics/
12. American Bar Association Formal Opinion 512 — Generative Artificial Intelligence Tools: https://www.americanbar.org/content/dam/aba/administrative/professional_responsibility/ethics-opinions/aba-formal-opinion-512.pdf

---

## Appendix G — Source Corpus Note

The prototype assumptions were **informed by** an illustrative sample under `docs/example/` (nine files, ~12 MB, flat directory). Treat that folder as **example evaluation material only** — not product scope, not the only real-world document mix, and not lawyer-final truth. Reusable gold structure: [`docs/example/gold/`](example/gold/README.md).

| File | Role |
|------|------|
| `EG90156.pdf` | Police collision report (~4 pages; scanned/image) |
| `Mayel Amini Dairyland Insurance 06.22.26.pdf` | Insurer correspondence (scanned) |
| `AMINI_MAYEL_20260706_eCW Medical Records.pdf` | Digital EMR-style medical export (~24 pages) |
| `AMINI_MAYEL_20260706_eCW Billing Ledger.pdf` | Claim-level CPT / billing ledger |
| `MEDICAL RECORDS- AMINI MAYEL DOI 03-28-2026- JACKMAN LAW FIRM.pdf` | Long scanned clinical/chiro stack (~67 pages) |
| `Demand Mayel Amini Final.docx` | Working demand with attorney review flags and TBD settlement |
| `Demand - Ahmed Ahmed.docx` | Completed-style demand (defect fixture: pronoun) |
| `Demand - Morris, Sandra.docx` | Completed-style demand (defect fixtures: empty RE/salutation, pronouns, exhibit gaps) |
| `Demand (Fernando Nicolas Fuentes).docx` | Completed-style demand (defect fixtures: pronouns, WPI brackets; aggravation theme) |

**Illustrative end-to-end sample:** Amini evidence PDFs + Amini demand as a *comparison* artifact (not authoritative input unless FR-CLS-06 enabled). Gold notes: [`docs/example/gold/amini-illustrative.md`](example/gold/amini-illustrative.md).

**Useful planted / observable defects for evaluation design:**

- Date-of-loss conflict (for example 3/20 vs 3/28) and fracture (X-ray) vs no fracture (MRI) flags in the Amini demand.
- `[SETTLEMENT AMOUNT - TBD]` and explicit `[FLAG FOR ATTORNEY REVIEW: …]` blocks.
- Carrier naming tension (Patriot in letter vs Dairyland-named PDF).
- Pronoun / RE / salutation defects in other demands.
- Exhibit references (photos, APS, liens) without matching standalone files in the folder.
- No standalone MRI PDF — imaging lives inside medical narrative/bundles.

For privacy, this specification treats the material as a controlled reference sample and does not reproduce unnecessary personal details. Keep these files out of public repositories and out of default LLM/logging pipelines.

---

## Final Foundation Rule

Build the evidence workspace first. Do not start by optimizing letter prose. A convincing prototype is one that can show where every fact came from, where the documents disagree, what the user decided, and why the final demand is safe to review.

**Extraction corollary (v0.2):** Prove OCR → spans → highlights → deterministic facts → human resolution on the reference corpus **before** enabling LLM extraction or polishing demand prose.
