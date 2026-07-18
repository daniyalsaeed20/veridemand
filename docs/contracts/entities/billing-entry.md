# Entity: BillingEntry

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.7 |
| Owning module(s) | [06 Chronology and Billing](../../modules/06-chronology-and-billing.md) |
| contracts_version | 0.1 |

## 1. Purpose

Service or financial line for ledger review and specials reconciliation.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `bil_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | |
| `document_id` | string | no | prefix `doc_` | Source ledger page |
| `provider` | string | no | | |
| `service_date` | string \| null | no | `YYYY-MM-DD` | |
| `code` | string \| null | no | CPT/HCPCS/etc. | |
| `description` | string | no | | |
| `charge` | string \| null | no | decimal string | |
| `payment` | string \| null | no | decimal string | |
| `adjustment` | string \| null | no | decimal string | |
| `balance` | string \| null | no | decimal string | |
| `currency` | string | yes | default `USD` | |
| `source_span_ids` | string[] | yes | default `[]` | |
| `reconciliation_ok` | bool \| null | no | | charge − payment − adjustment vs balance |
| `reconciliation_note` | string | no | | When mismatch |
| `fact_ids` | string[] | no | | Linked facts |

## 3. Validation rules

- All money fields are decimal **strings** in JSON.
- Arithmetic in code using Decimal; never trust LLM math.
- Ambiguity → visible issue, not silent fix.

## 4. Example JSON

```json
{
  "id": "bil_01JEXAMPLE0000000000000F1",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "document_id": "doc_01JEXAMPLE000000000000003",
  "provider": "Example Clinic",
  "service_date": "2026-04-02",
  "code": "99213",
  "description": "Office visit",
  "charge": "150.00",
  "payment": "0.00",
  "adjustment": "0.00",
  "balance": "150.00",
  "currency": "USD",
  "source_span_ids": ["span_01JEXAMPLE0000000000000B9"],
  "reconciliation_ok": true,
  "reconciliation_note": null,
  "fact_ids": []
}
```

## 5. Open / additive notes

Claimed medical specials total may be a separate user-confirmed fact (`damages.specials_claimed`), not auto-derived when ambiguous (FR-BIL-04).
