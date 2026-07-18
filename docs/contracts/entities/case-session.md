# Entity: CaseSession

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.1 |
| Owning module(s) | [01 Session and Workspace](../../modules/01-session-and-workspace.md) |
| contracts_version | 0.1 |

## 1. Purpose

Temporary in-memory case workspace. Session-only; deleted on TTL, reset, or explicit delete.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `ses_` | Opaque ULID/UUID-style |
| `created_at` | datetime | yes | ISO-8601 UTC | |
| `expires_at` | datetime | yes | `> created_at` | From TTL |
| `last_activity_at` | datetime | yes | | Touched on activity |
| `status` | SessionStatus | yes | see [enums](../enums.md) | Workflow state |
| `settings` | object | yes | subset of AppSettings | Session-scoped overrides if any |
| `warning` | string | no | | e.g. refresh-may-lose-work banner text |

**Server-only (not in API JSON):** workspace filesystem path under temp root.

## 3. Validation rules

- Never return local paths in API payloads.
- Expired sessions reject scoped operations with a clear error.

## 4. Example JSON

```json
{
  "id": "ses_01JEXAMPLE000000000000000",
  "created_at": "2026-07-18T12:00:00Z",
  "expires_at": "2026-07-18T14:00:00Z",
  "last_activity_at": "2026-07-18T12:15:00Z",
  "status": "created",
  "settings": {
    "ocr_render_dpi": 200,
    "enable_llm_semantic_extraction": false
  },
  "warning": "This temporary session may be lost on refresh or expiry."
}
```

## 5. Open / additive notes

Collections of documents/facts/issues live in session memory keyed by `id`; they are separate entities, not embedded blobs in this contract.
