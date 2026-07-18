# Entity: PreflightFinding / PreflightReport

| Field | Value |
|-------|-------|
| Spec | §8.11 / Phase 9 |
| Owning module(s) | [10 Verification, Preflight, and Export](../../modules/10-verification-preflight-and-export.md) |
| contracts_version | 0.1 |

## 1. Purpose

Programmatic gate before final export: identity, medical, billing math, placeholders/TBD, exhibits, sentence support, and unresolved Red issues. Semantic verification (when enabled) may add findings but must not override a failed programmatic gate.

## 2. Fields — PreflightFinding

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | no | prefix `find_` | Opaque; optional if list is report-scoped |
| `code` | string | yes | see finding codes below | Prefer dotted codes aligned with [issue-types.md](../issue-types.md) |
| `severity` | FindingSeverity | yes | `info` \| `warning` \| `error` | enum |
| `blocking` | bool | yes | | `true` blocks final export |
| `message` | string | yes | non-empty | User-facing |
| `draft_ref` | object \| null | no | `{ paragraph_id, sentence_index? }` | Link into draft |
| `fact_ids` | string[] | no | | Related facts |
| `source_span_ids` | string[] | no | default `[]` | |
| `document_ids` | string[] | no | | |
| `semantic_label` | StatementSupportLabel \| null | no | enum | When support validator ran |
| `issue_id` | string \| null | no | prefix `issue_` | When finding mirrors an Issue |

## 3. Fields — PreflightReport

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `preflight_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | |
| `draft_id` | string | yes | prefix `draft_` | |
| `programmatic_gate` | string | yes | `pass` \| `blocked` | Deterministic gate result |
| `findings` | PreflightFinding[] | yes | | |
| `created_at` | datetime | yes | ISO-8601 UTC | |
| `semantic_ran` | bool | no | | Optional verifier invoked |
| `semantic_error` | string \| null | no | | Provider/schema failure message; must not flip gate to pass |

## 4. Finding codes (additive)

Prefer reusing [issue-types.md](../issue-types.md) where the finding is the same defect. Additional preflight-only codes:

| code | Typical severity | blocking | Notes |
|------|------------------|----------|-------|
| `draft.placeholder` | error | yes | TBD / placeholders |
| `draft.unsupported_statement` | error | yes | Case-specific fact without support |
| `draft.contradicted_statement` | error | yes | |
| `billing.total_mismatch` | error | yes | |
| `exhibits.listed_missing` | error/warning | often yes | |
| `support.unsupported_sentence` | error | yes | Sentence-level; maps to draft unsupported policy |
| `support.partially_supported_sentence` | warning | policy | May block final if firm policy requires full support |
| `identity.missing_required_field` | error | yes | Preflight identity checklist |
| `medical.missing_required_field` | warning/error | criticality | |
| `issue.unresolved_red` | error | yes | Open/waived-without-policy Red issue |

## 5. Validation rules

- `can_final_export` is false if any `blocking` finding exists or `programmatic_gate == "blocked"`.
- Semantic verifier failures → non-authoritative warning / `semantic_error`; never clear a blocked programmatic gate.
- Finding `code` values are additive; do not silently rename without changelog.

## 6. Example JSON

```json
{
  "id": "preflight_01JEXAMPLE0000000000000P1",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "draft_id": "draft_01JEXAMPLE0000000000000A1",
  "programmatic_gate": "blocked",
  "created_at": "2026-07-18T15:00:00Z",
  "semantic_ran": false,
  "semantic_error": null,
  "findings": [
    {
      "code": "draft.placeholder",
      "severity": "error",
      "blocking": true,
      "message": "Replace TBD before final export.",
      "draft_ref": { "paragraph_id": "para_4", "sentence_index": 0 },
      "fact_ids": [],
      "source_span_ids": [],
      "semantic_label": null,
      "issue_id": null
    },
    {
      "code": "support.unsupported_sentence",
      "severity": "error",
      "blocking": true,
      "message": "Case-specific factual sentence has no approved support.",
      "draft_ref": { "paragraph_id": "para_7", "sentence_index": 1 },
      "fact_ids": [],
      "source_span_ids": [],
      "semantic_label": "unsupported",
      "issue_id": null
    }
  ]
}
```

## 7. Open / additive notes

- `FindingSeverity` and `StatementSupportLabel` live in [enums.md](../enums.md).
- Export refusal uses API codes `export_blocked_preflight` / `export_blocked_red_issues` in [error-codes.md](../error-codes.md).
