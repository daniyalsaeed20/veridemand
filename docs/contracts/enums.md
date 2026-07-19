# Shared Enums

**contracts_version:** `0.1`  
Closed enums unless noted. Values are lowercase `snake_case` in JSON.

---

## SessionStatus

Canonical workflow states from prototype §5.1, plus additive terminal states.

| Value | Meaning |
|-------|---------|
| `created` | Session initiated; upload allowed |
| `ingesting` | Files submitted; validation in progress |
| `processing` | Extraction / OCR / classification / facts running |
| `reviewing` | Facts and issues available for human review |
| `draftable` | Required facts approved; may generate draft |
| `draft_review` | Draft exists; edit / verify / preflight |
| `exportable` | Blockers resolved; final export allowed |
| `expired` | TTL exceeded or cleared; data deleted or pending cleanup |
| `failed` | Terminal processing failure (additive beyond §5.1; session may still be reset/deleted) |
| `deleted` | Explicitly deleted (additive beyond §5.1) |

**Never emit `active`.** That obsolete alias must not appear in API payloads or new module prose. Map any legacy reference to the precise workflow state (`created`, `reviewing`, etc.). Do not invent new public statuses without updating this table.

---

## DocumentStatus

| Value | Meaning |
|-------|---------|
| `uploaded` | Accepted into session storage |
| `duplicate` | Exact SHA-256 match of another document in session |
| `rejected` | Failed validation (type, signature, encryption, limits) |
| `normalized` | Canonical view + page count/thumbnails ready |
| `ready_for_extraction` | Eligible for page analysis |
| `extracting` | Page extraction in progress |
| `extracted` | Pages/tokens/spans available |
| `classified` | Classification assigned (may still be user-corrected) |
| `excluded` | User excluded from drafting/evidence |

---

## DocumentFileType

| Value | Meaning |
|-------|---------|
| `pdf` | PDF |
| `docx` | Word DOCX |
| `jpg` | JPEG image |
| `png` | PNG image |
| `tiff` | TIFF image |

---

## DocumentClassification

From FR-CLS-03. Additive category list.

| Value | Meaning |
|-------|---------|
| `police_report` | Police / collision report |
| `insurer_correspondence` | Carrier letters |
| `medical_record` | Clinical / EMR / chiro stacks |
| `imaging_report` | Standalone imaging (often embedded in medical_record) |
| `bill_ledger` | Bills / CPT ledgers |
| `lien` | Lien documents |
| `wage_loss` | Wage-loss material |
| `photographs` | Injury / scene photos |
| `existing_demand` | Prior demand draft (not authoritative unless FR-CLS-06) |
| `template` | Firm demand template |
| `other` | Unclassified / other |

---

## ExtractionMethod

| Value | Meaning |
|-------|---------|
| `native` | Native PDF text layer |
| `ocr` | PaddleOCR (or equivalent local printed OCR) |
| `manual` | User-drawn or user-entered source |

---

## PageRoute

| Value | Meaning |
|-------|---------|
| `native` | Use native extraction |
| `ocr` | Render + OCR |
| `manual_review` | Insufficient text; human required |

---

## OcrStatus

Closed vocabulary for `DocumentPage.ocr_status` (contracts win over module samples that used `completed`).

| Value | Meaning |
|-------|---------|
| `not_needed` | Native path; OCR not required |
| `pending` | Routed for OCR; not yet completed |
| `done` | OCR finished (may still carry quality warnings) |
| `failed` | OCR hard-failed or produced no usable text after attempts |

---

## FactStatus

From prototype §7.5.

| Value | Meaning | Allowed use in final draft |
|-------|---------|----------------------------|
| `suggested` | Auto-extracted, not yet reviewed | Not for critical facts |
| `verified` | High-confidence / user-confirmed | Yes |
| `edited` | User changed value | Yes (show history) |
| `conflicting` | Sources disagree | No until resolved |
| `needs_review` | Low confidence or incomplete | Depends on criticality |
| `rejected` | Wrong / irrelevant | No |
| `locked` | Attorney-approved; protected | Yes (authoritative) |

---

## IssueSeverity

Maps prototype Green / Amber / Red review states.

| Value | Meaning |
|-------|---------|
| `green` | Informational / resolved / non-blocking |
| `amber` | Needs confirmation; may continue |
| `red` | Blocks dependent workflow until resolved or waived |

---

## IssueStatus

| Value | Meaning |
|-------|---------|
| `open` | Unresolved |
| `resolved` | User selected a resolution |
| `waived` | Explicitly waived (still recorded) |
| `deferred` | Deferred to attorney / later |

---

## ReviewState

UI aggregate for a fact or queue item (FR-REV-01).

| Value | Meaning |
|-------|---------|
| `green` | Acceptable |
| `amber` | Confirm |
| `red` | Block / must act |

---

## TimelineEventType

| Value | Meaning |
|-------|---------|
| `collision` | Collision / DOL event |
| `treatment` | Treatment encounter |
| `imaging` | Imaging study |
| `correspondence` | Insurer / counsel correspondence |
| `billing` | Billing / payment event |
| `discharge` | Discharge / MMI-related |
| `settlement` | Settlement / demand-related |

---

## DraftSectionType

| Value | Meaning |
|-------|---------|
| `header_re` | Header / RE line |
| `facts` | Facts narrative |
| `liability` | Liability |
| `treatment_summary` | Injuries / treatment by provider |
| `general_damages` | General damages |
| `specials_table` | Specials / medical specials |
| `settlement_proposal` | Settlement demand |
| `closing` | Closing |
| `exhibit_list` | Exhibits |
| `other` | Firm-specific extra section |

---

## StatementSupportLabel

For verification (FR-VAL-02), when enabled.

| Value | Meaning |
|-------|---------|
| `supported` | Fully supported by approved facts |
| `partially_supported` | Partial support |
| `unsupported` | No adequate evidence |
| `contradicted` | Conflicts with approved evidence |
| `legal_clause` | Template legal language |
| `argument` | Argumentative / non-factual |

---

## HealthStatus

| Value | Meaning |
|-------|---------|
| `ok` | Healthy |
| `degraded` | Running with reduced capability |
| `error` | Unhealthy |

---

## DecisionAction

Actions recorded on [`UserDecision`](./entities/user-decision.md) (module 08). Additive.

| Value | Meaning |
|-------|---------|
| `verify` | Confirm extracted value without change |
| `edit` | Change value (with reason) |
| `use_value` | Select one of the conflicting suggested values |
| `enter_value` | Enter a new value (often with manual source) |
| `exclude` | Exclude fact/document from drafting |
| `mark_unavailable` | Mark field as unavailable / illegible after attempt |
| `resolve` | Resolve an issue with a listed option |
| `waive` | Explicitly waive (still recorded) |
| `defer_attorney` | Defer to attorney |
| `lock` | Lock fact as attorney-approved |

---

## FindingSeverity

Preflight finding severity ([`PreflightFinding`](./entities/preflight-report.md)).

| Value | Meaning |
|-------|---------|
| `info` | Informational; non-blocking |
| `warning` | Needs attention; may block per policy |
| `error` | Gate failure when `blocking` is true |

---

## ExportKind

| Value | Meaning |
|-------|---------|
| `draft` | Working export; may allow noncritical warnings with draft label |
| `final` | Final deliverable; requires passing programmatic preflight gate |
