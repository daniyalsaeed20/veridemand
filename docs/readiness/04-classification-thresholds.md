# Phase 4 — Classification thresholds (provisional)

**Status:** `0.1-provisional` — measured on synthetic fixtures; not a corpus SLA.

## Rule score (wire field `classification_confidence`)

| Setting | Default | Env var | Notes |
|---------|---------|---------|-------|
| `rule_confidence_threshold` | `0.55` | `RULE_CONFIDENCE_THRESHOLD` | Heuristic **rule score** cutoff — **not** a calibrated probability. Below threshold → review; conflicts/safety can force review even when score ≥ 0.55 |

UI label: **Rule score**. Do not present as “85% confident.”

## Safety archetype (Stage A)

Independent of winning taxonomy category. Material demand/template/derivative signals force non-authoritative defaults (FR-CLS-06) even if Stage B predicts an evidence type.

## LLM classification

| Setting | Default | Env var | Notes |
|---------|---------|---------|-------|
| `enable_llm_classification` | `false` | `ENABLE_LLM_CLASSIFICATION` | Live fallback **deferred** (OD-12); stub validates request/response only |

## Rule precedence (summary)

1. Stage A demand/template/derivative safety (authority restriction)
2. Stage B taxonomy scores; demand/template archetype overrides evidence category labels when structural families match
3. Filename tokens (capped; cannot alone override contradictory content)
4. Weak single keywords insufficient alone
5. Medical bundles with embedded imaging remain `medical_record`
6. Close scores, archetype-vs-category, and limited usable text force ambiguity regardless of absolute score

## Sequence policy (provisional)

Category rank → upload-order tie-break → contiguous `sequence_index`. Existing demand and template documents trail evidence categories but remain visible. Sequence does **not** imply authority.

## Measurement notes

- Threshold chosen for Phase 4 MVP per OD-06 option B (rules-only until corpus measurement).
- Phase 4 hardening (2026-07-20): conflict-aware review + classification-independent FR-CLS-06 safety.
