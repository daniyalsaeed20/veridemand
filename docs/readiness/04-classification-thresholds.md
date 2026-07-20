# Phase 4 — Classification thresholds (provisional)

**Status:** `0.1-provisional` — measured on synthetic fixtures; not a corpus SLA.

## Rule confidence threshold

| Setting | Default | Env var | Notes |
|---------|---------|---------|-------|
| `rule_confidence_threshold` | `0.55` | `RULE_CONFIDENCE_THRESHOLD` | Below → Amber `classification.ambiguous` Issue; optional LLM when enabled |

## LLM classification

| Setting | Default | Env var | Notes |
|---------|---------|---------|-------|
| `enable_llm_classification` | `false` | `ENABLE_LLM_CLASSIFICATION` | Live fallback **deferred** (OD-12); stub validates request/response only |

## Rule precedence (summary)

1. Existing demand / template structural signals
2. Strong domain content (police, insurer, eCW medical/billing, etc.)
3. Filename tokens (capped; cannot alone override contradictory content)
4. Weak single keywords insufficient alone
5. Medical bundles with embedded imaging remain `medical_record`

## Sequence policy (provisional)

Category rank → upload-order tie-break → contiguous `sequence_index`. Existing demand and template documents trail evidence categories but remain visible.

## Measurement notes

- Threshold chosen for Phase 4 MVP per OD-06 option B (rules-only until corpus measurement).
- Revisit after reference-package manual correction timings are recorded in `phase-04-completion.md`.
