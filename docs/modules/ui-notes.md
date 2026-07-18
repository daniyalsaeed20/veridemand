# Light UI Notes (Cross-Cutting)

| Field | Value |
|-------|-------|
| Status | design |
| Spec | Prototype §13 (product narrative) |
| SoT role | **Implementer SoT** for panel behavior and recovery UX. Prototype §13 remains product narrative. User-facing API messages: [`error-codes.md`](../contracts/error-codes.md) wins. |
| Errors | [`docs/contracts/error-codes.md`](../contracts/error-codes.md) |
| Issues | [`docs/contracts/issue-types.md`](../contracts/issue-types.md) |
| Enums (ReviewState, …) | [`docs/contracts/enums.md`](../contracts/enums.md) |
| Contracts index | [`docs/contracts/README.md`](../contracts/README.md) |
| Step ↔ module map | [`README.md`](./README.md#phase--module--ui-crosswalk) |

## Purpose

Lightweight UX contract for implementers of the React workspace. **Not** a visual design system or TipTap pixel spec. Complements module docs 01–10 (workspace) and [12 evaluation](./12-evaluation-demonstration.md) (CLI/report only — no primary workspace step).

`docs/example/` remains illustrative sample material only.

---

## 1. Global chrome

| Element | Behavior |
|---------|----------|
| **Temporary Prototype** banner | Always visible; state product is not sole final legal review (§15.3). |
| Session warning | On create and periodically: refresh/expiry may lose work (FR-SES-05). |
| Error toasts | Show `message` from API `error_code`; optional “Details / ID” for `request_id`. |
| Red blockers | Must not auto-dismiss in a way that hides export/draft blockers. |
| Logging | Do not display full page OCR text in toasts; respect `LOG_DOCUMENT_TEXT=false`. |

Green / Amber / Red review states (FR-REV-01) use [`IssueSeverity` / `ReviewState`](../contracts/enums.md). Queue SoT is [`Issue`](../contracts/entities/issue.md).

---

## 2. Navigation steps (§13.2)

| Step | Screen | Primary modules | Primary signals | Errors / issues |
|------|--------|-----------------|-----------------|-----------------|
| 1 | Documents | 02, 03, 04 | Upload progress, classification, sequence, page quality | Upload `error_code`s; duplicate status; page quality flags → Issues |
| 2 | Facts | 05, 08 | Grouped facts, confidence, sources | `fact_*` API errors; Amber/Red facts open Issues |
| 3 | Timeline & Billing | 06 | Events, ledger, reconciliation | Billing mismatch → Issues; not silent fix |
| 4 | Issues | 07, 08 | Severity-sorted queue | Resolutions; side-by-side sources (module 08) |
| 5 | Demand | 09 | Generate / edit / support map | `draft_not_ready`, schema failure; support clicks → Facts/Viewer |
| 6 | Preflight | 10 | Validation matrix, export | `export_blocked_*`; CTA opens Issues / offending paragraph |

Full Phase ↔ Module ↔ UI crosswalk: [`README.md`](./README.md#phase--module--ui-crosswalk).

---

## 3. Panels (brief)

### Documents

- Show per-file status and user-facing upload errors (same codes as catalog).
- Page quality warning counts link into Issues or page list.
- Classification correction and reorder without reprocessing (module 04).

### Facts

- Click fact → Source Viewer highlight (module 03/08).
- Show provenance: extracted / calculated / user-supplied.
- Locked facts: show lock; edits return `fact_locked` if disallowed.

### Issues

- Title first, then explanation, sources, actions.
- Red + `blocking` gate Draftable/Exportable states (§5.1).
- List is contracted `Issue` entities (`GET /issues`), not a separate persisted type.

### Source Viewer

- PDF.js: zoom, page nav, highlight polygons, method + confidence beside page.
- Manual rectangle → create span (module 08); do not mark verified until user confirms.

### Demand / Preflight

- Prefer **docxtpl DOCX** download as first deliverable; TipTap secondary (module 09).
- Label **Draft Export** vs **Final Export** clearly (§12.4).
- Final blocked → list blockers with links to Issues; use messages from `export_blocked_*`.

---

## 4. Recovery map (§13.8)

Cite `error_code` only — do not hardcode divergent user prose here. Messages live in [`error-codes.md`](../contracts/error-codes.md).

| Condition | `error_code` | UI recovery |
|-----------|--------------|-------------|
| Unsupported file | `upload_unsupported_type` | Remove/convert; show on Documents |
| Encrypted PDF | `upload_encrypted_pdf` | Prompt unlocked copy |
| Extraction failure | page/extraction warnings → Issues | Open page warnings / Issues; manual entry |
| LLM schema failure | `draft_llm_schema_failed` | Retry once; keep prior draft/evidence; show `request_id` |
| Session expiry | `session_expired` | Force new session flow |
| Export blocker | `export_blocked_*` | Navigate to Issues / Preflight |

Full code list: [error-codes.md](../contracts/error-codes.md).

---

## 5. Out of scope (this doc)

- Color palette, typography, motion system  
- TipTap toolbar / paragraph UX polish  
- Full accessibility audit (consider WCAG later)  
- Multi-user presence / auth UI  
- Evaluation dashboard UI (module 12 is CLI/report-first)

---

## Changelog

| Date | Change |
|------|--------|
| 2026-07-18 | Initial light UI notes (Pass 5) |
| 2026-07-19 | SoT split vs §13; crosswalk link; Issue queue; recovery cites codes only |
