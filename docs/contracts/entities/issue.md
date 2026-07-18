# Entity: Issue

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.8 / §11 |
| Owning module(s) | [07 Issue Engine](../../modules/07-issue-and-contradiction-engine.md), [08 Human Review](../../modules/08-human-review-and-manual-intervention.md) |
| contracts_version | 0.1 |

## 1. Purpose

Conflict, uncertainty, missing information, or draft defect requiring user action.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `issue_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | |
| `issue_type` | string | yes | see [issue-types.md](../issue-types.md) | Additive |
| `severity` | IssueSeverity | yes | `green` \| `amber` \| `red` | |
| `title` | string | yes | non-empty | Concise |
| `explanation` | string | yes | | Longer detail |
| `source_span_ids` | string[] | yes | default `[]` | Evidence |
| `fact_ids` | string[] | no | | Related facts |
| `document_ids` | string[] | no | | |
| `options` | string[] | no | resolution option codes | |
| `blocking` | bool | yes | | Blocks draft/export when true |
| `status` | IssueStatus | yes | enum | |
| `resolution` | object \| null | no | `{ option, note, at, actor }` | When resolved/waived |

## 3. Validation rules

- Exact conflicts must not auto-pick a winning source.
- LLM may propose issues only as optional assistance; never final legal judgment.

## 4. Example JSON

```json
{
  "id": "issue_01JEXAMPLE0000000000000D1",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "issue_type": "collision.date_of_loss_conflict",
  "severity": "red",
  "title": "Two dates of loss were found",
  "explanation": "Police report and one provider note disagree on the collision date.",
  "source_span_ids": ["span_01JEXAMPLE0000000000000B1", "span_01JEXAMPLE0000000000000B2"],
  "fact_ids": ["fact_01JEXAMPLE0000000000000C1", "fact_01JEXAMPLE0000000000000C2"],
  "document_ids": ["doc_01JEXAMPLE000000000000001", "doc_01JEXAMPLE000000000000002"],
  "options": ["use_source_a", "use_source_b", "enter_other", "mark_unresolved"],
  "blocking": true,
  "status": "open",
  "resolution": null
}
```

## 5. Open / additive notes

Option codes are additive per `issue_type`; keep stable once used in gold tests.
