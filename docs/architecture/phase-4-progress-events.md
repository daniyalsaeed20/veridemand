# Phase 4 progress events (Correction 4)

Public progress ownership, page identity, and operation-attempt lifecycle.

## Ownership

`ProcessingCoordinator` is the sole publisher of public extraction lifecycle
events over SSE (`EventBroker`). Internal services
(`NativeExtractionService`, `VisualOcrService`, `OcrWorkerManager`) emit
diagnostic callbacks and logs only.

## Page identifiers

| Field | Meaning |
|---|---|
| `document_page_number` | Absolute 1-based canonical document page |
| `document_pages_total` | Canonical page count |
| `selected_page_index` | 1-based index within the current work category |
| `selected_pages_total` | Count of pages selected for that category |
| `visual_page_index` / `visual_pages_total` | Selected visual OCR subset |

Never pair absolute `page_number` with a selected-work `pages_total` as if they
shared one coordinate system. Legacy `page_number` aliases
`document_page_number`; legacy `pages_total` aliases selected count and is
deprecated for UI pairing.

## Operation attempt lifecycle

Each attempt identity includes `operation_id`, `document_id`,
`document_page_number` (when applicable), `operation`, `attempt_number`, and
`worker_generation`.

Invariants (enforced by `OperationLifecycleLedger`):

- queued ≤ 1
- started = 1 (except documented skip-without-start)
- terminal ≤ 1
- terminal events never return to queued/started under the same attempt
- retries mint a new attempt number and `operation_id`

## Sequence and versioning

- `event_sequence` strictly increases per session (broker-owned)
- `progress_version` increases when authoritative progress state changes
- heartbeats may increase `event_sequence` without advancing `progress_version`
- SSE `id` carries `event_id`; reconnect honours `Last-Event-ID` and bounded
  replay, otherwise sends the newest authoritative snapshot

See also ADRs 0029–0033 and `phase-4-live-time-and-eta.md`.
