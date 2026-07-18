# Entity: UserDecision

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.9 / §11 / §15.4 |
| Owning module(s) | [08 Human Review](../../modules/08-human-review-and-manual-intervention.md) |
| contracts_version | 0.1 |

## 1. Purpose

Audit record of manual intervention during the session (deleted with session).

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `dec_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | |
| `target_type` | string | yes | `fact` \| `issue` \| `document` \| `span` \| `billing` \| `draft` | |
| `target_id` | string | yes | opaque id of target | |
| `action` | DecisionAction | yes | enum in [enums.md](../enums.md) | |
| `old_value` | string \| object \| null | no | | Snapshot |
| `new_value` | string \| object \| null | no | | Snapshot |
| `reason` | string | no | | User/attorney note |
| `timestamp` | datetime | yes | ISO-8601 UTC | |
| `actor_role` | string | no | `paralegal` \| `attorney` \| `system` | Prototype may omit auth |

## 3. Validation rules

- Decision log is session-scoped and must not be written to durable DB in prototype.
- Do not log full page text by default (`LOG_DOCUMENT_TEXT=false`).

## 4. Example JSON

```json
{
  "id": "dec_01JEXAMPLE0000000000000I1",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "target_type": "issue",
  "target_id": "issue_01JEXAMPLE0000000000000D1",
  "action": "resolve",
  "old_value": { "status": "open" },
  "new_value": { "status": "resolved", "option": "use_source_a" },
  "reason": "Police report is authoritative for DOL",
  "timestamp": "2026-07-18T12:40:00Z",
  "actor_role": "paralegal"
}
```

## 5. Open / additive notes

Action vocabulary is additive; keep codes stable for demos.
