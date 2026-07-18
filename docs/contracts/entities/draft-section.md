# Entity: DraftSection

| Field | Value |
|-------|-------|
| Spec | §7.2 / §8.10 / §12.2 |
| Owning module(s) | [09 Demand Generation](../../modules/09-demand-generation.md) |
| contracts_version | 0.1 |

## 1. Purpose

One structured section of a demand draft with paragraph-level evidence links.

## 2. Fields

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `sec_` | Opaque |
| `draft_id` | string | yes | prefix `draft_` | Parent draft |
| `section_type` | DraftSectionType | yes | enum | |
| `heading` | string | yes | | Display heading |
| `order_index` | int | yes | `>= 0` | |
| `paragraphs` | DraftParagraph[] | yes | | See nested shape |

### DraftParagraph (nested)

| Name | Type | Required | Constraints | Notes |
|------|------|----------|-------------|-------|
| `id` | string | yes | prefix `para_` | |
| `text` | string | yes | | |
| `supporting_fact_ids` | string[] | yes | nonempty for case-specific factual paras | FR-DRF-03 |
| `contains_argument` | bool | yes | default false | |
| `verification_required` | bool | yes | default false | After user edit |
| `support_label` | StatementSupportLabel | no | after verify | |

## 3. Validation rules

- Case-specific factual paragraphs must map to approved facts.
- Template legal clauses may have empty `supporting_fact_ids` only when marked as legal clause / non-factual.

## 4. Example JSON

```json
{
  "id": "sec_01JEXAMPLE0000000000000G1",
  "draft_id": "draft_01JEXAMPLE0000000000000H1",
  "section_type": "treatment_summary",
  "heading": "SUMMARY OF INJURIES AND TREATMENT",
  "order_index": 3,
  "paragraphs": [
    {
      "id": "para_01JEXAMPLE0000000000000P1",
      "text": "The client treated with Example Clinic beginning April 2, 2026.",
      "supporting_fact_ids": ["fact_01JEXAMPLE0000000000000C3"],
      "contains_argument": false,
      "verification_required": false,
      "support_label": null
    }
  ]
}
```

## 5. Open / additive notes

Parent `DemandDraft` object (id, template_id, status, sections[]) may be defined in module 09; sections are the reusable contract unit here.
