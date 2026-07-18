# Entity: TimelineEvent

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.7 |
| Owning module(s) | [06 Chronology and Billing](../../modules/06-chronology-and-billing.md) |
| contracts_version | 0.1 |

## 1. Purpose

Chronological event derived from dated facts for review and drafting.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `evt_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | |
| `event_type` | TimelineEventType | yes | enum | |
| `event_date` | string \| null | no | `YYYY-MM-DD` or null | Unknown/approximate allowed |
| `event_time` | string \| null | no | `HH:MM` optional | |
| `date_precision` | string | no | `exact` \| `approximate` \| `unknown` | |
| `summary` | string | yes | | Short description |
| `fact_ids` | string[] | yes | | Supporting facts |
| `provider_name` | string | no | | When treatment-related |
| `sort_key` | string | no | | Stable sort aid |

## 3. Validation rules

- Sort by normalized date; preserve unknown/approximate without inventing dates.
- `fact_ids` should reference existing session facts.

## 4. Example JSON

```json
{
  "id": "evt_01JEXAMPLE0000000000000E1",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "event_type": "collision",
  "event_date": "2026-03-28",
  "event_time": null,
  "date_precision": "exact",
  "summary": "Reported motor-vehicle collision",
  "fact_ids": ["fact_01JEXAMPLE0000000000000C1"],
  "provider_name": null,
  "sort_key": "2026-03-28T00:00:00Z"
}
```

## 5. Open / additive notes

Provider treatment ranges may be separate summary objects later; v0.1 keeps ranges as facts + events.
