# ADR 0075 — Strict label-transfer rules for detector-first crops

## Status

Accepted (Phase 5 Task C0)

## Context

Existing human labels were collected on post-recognition crops. Automatically
copying labels by loose page proximity would poison the detector-first pool.

## Decision

Transfer a label only when:

1. **Exact crop identity** — crop SHA-256 matches; or
2. **Strict geometry identity** — source bbox within tight L∞ and IoU
   tolerances **and** crop framing still matches under the same IoU bar.

Loose overlap is counted as rejected and does not transfer. Material crop
framing differences leave the new crop unlabelled. Private provenance records
old/new hashes, method, overlap score, and label provenance.

## Consequences

Transferable label counts will be lower than total detector regions. Unlabelled
detector-first crops require fresh human review before training.
