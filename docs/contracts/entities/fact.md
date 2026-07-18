# Entity: Fact

| Field | Value |
|-------|-------|
| Spec | §7.2 / §7.4 / §7.5 / §8.5 |
| Owning module(s) | [05 Deterministic Fact Extraction](../../modules/05-deterministic-fact-extraction.md), [08 Human Review](../../modules/08-human-review-and-manual-intervention.md) |
| contracts_version | 0.1 |
| Deprecated alias | `FactCandidate` — do not use in new APIs; use `Fact` + `FactStatus` |

## 1. Purpose

Normalized case fact with provenance. System of record for drafting inputs once status allows.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `fact_` | Opaque |
| `session_id` | string | yes | prefix `ses_` | |
| `fact_type` | string | yes | see [fact-types.md](../fact-types.md) | Additive catalog |
| `raw_value` | string | yes | | As seen in evidence / user entry |
| `normalized_value` | string \| number \| null | no | typed per fact_type | e.g. `YYYY-MM-DD`, decimal string for money |
| `display_value` | string | no | | Human-readable |
| `description` | string | no | | Short explanation |
| `confidence` | float | yes | `0–1` | |
| `status` | FactStatus | yes | enum §7.5 | |
| `source_span_ids` | string[] | yes | may be empty only if user-supplied with reason | Prefer ≥1 for extracted |
| `extraction_methods` | string[] | yes | e.g. `regex`, `context_parser`, `user` | |
| `document_ids` | string[] | no | derived from spans | Convenience |
| `label_context` | string | no | | Nearby label text |
| `criticality` | string | no | `critical` \| `normal` | Drives Amber/Red policy |
| `user_override` | object \| null | no | `{ value, reason, at }` | When edited |
| `provenance` | string | no | `deterministic` \| `calculated` \| `user` \| `llm_optional` | Default deterministic |

## 3. Validation rules

- No invented values: extracted facts must cite real `source_span_ids` when not user-supplied.
- Critical facts with low confidence or conflict → `needs_review` / `conflicting`, never silent accept.
- `locked` facts must not be overwritten by automatic re-extraction.

## 4. Example JSON

```json
{
  "id": "fact_01JEXAMPLE0000000000000C1",
  "session_id": "ses_01JEXAMPLE000000000000000",
  "fact_type": "collision.date",
  "raw_value": "03/28/2026",
  "normalized_value": "2026-03-28",
  "display_value": "March 28, 2026",
  "description": "Reported date of the collision.",
  "confidence": 0.99,
  "status": "verified",
  "source_span_ids": ["span_01JEXAMPLE0000000000000B1"],
  "extraction_methods": ["regex", "context_parser"],
  "document_ids": ["doc_01JEXAMPLE000000000000001"],
  "label_context": "Date of Loss",
  "criticality": "critical",
  "user_override": null,
  "provenance": "deterministic"
}
```

## 5. Open / additive notes

Money `normalized_value` should be a decimal string when serialized in JSON. Semantic LLM provenance is optional and deferred (`llm_optional`).
