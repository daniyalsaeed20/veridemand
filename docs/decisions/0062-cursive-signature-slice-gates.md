# ADR 0062 — Cursive and signature safety-slice gates

## Status

Accepted (Phase 5 Task B2)

**Failed baseline — superseded for the current release path** (later B3/B4 eras also failed; release architecture is ADRs 0082–0087). No `production_candidate` classifier shipped.

## Context

Project handwriting seeds include cursive (22) and signatures (11). Aggregate
safe-bypass can hide slice failures where cursive or signatures route to
`printed` (Paddle leak) or `non_text` (discarded instead of reserved for
Phase 6).

## Decision

1. On project source-group-isolated OOF predictions, require:
   - cursive routed `printed` count = 0
   - signature routed `printed` count = 0
   - cursive routed `non_text` count = 0
   - signature routed `non_text` count = 0
2. Cursive/signature may route to `handwritten` or `uncertain` only.
3. Report per-slice routed outcomes for digits, hand-printed, cursive,
   signatures, and longer notes using seed `source_category` tags.
4. Slice gates are hard requirements alongside the Task B aggregate gates
   (handwritten→printed = 0, safe-bypass = 100%, non_text→printed = 0,
   printed retention ≥ 80%). Do not weaken aggregate gates.

## Consequences

- A configuration that only improves handprint/digit recall cannot pass if
  cursive or signatures still leak or are discarded.
- Failure reporting must distinguish cursive, signature, digit, and general
  printed/handwritten confusion.

## Related

- ADR 0057 (prototype threshold safety gates)
- ADR 0059 (ASAP supplementation)
