# ADR 0066 — Conflict-to-uncertain decision policy

## Status

Accepted (Phase 5 Task B3)

## Context

Independent risks can both be elevated, land in grey zones, or conflict. The
runtime must still expose only the four public outcomes and must never discard
material handwriting risk as non_text.

## Decision

Deterministic precedence:

```text
if output invalid / non-finite / wrong shape:
    uncertain
elif p_hw >= handwriting_accept and p_nt < non_text_accept:
    handwritten
elif p_hw <= handwriting_safe_low and p_nt >= non_text_accept:
    non_text
elif p_hw <= handwriting_safe_low and p_nt <= non_text_safe_low:
    printed
else:
    uncertain
```

Ordering constraints:

```text
handwriting_safe_low < handwriting_accept
non_text_safe_low < non_text_accept
```

Material handwriting risk must never become `non_text`. Both risks above accept
thresholds → `uncertain`. Invalid output, NaN, infinity, inference failure, and
model unavailability under enforced mode → `uncertain`.

## Consequences

Existing `HandwritingDecisionReason` codes remain sufficient
(`*_threshold_met`, `threshold_conflict`, `low_top_probability`,
`invalid_output`, …). Public outcome enums are unchanged.
