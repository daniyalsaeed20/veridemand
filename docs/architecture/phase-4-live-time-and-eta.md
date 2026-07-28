# Phase 4 live time and ETA (Correction 4)

## Separate clocks

Backend monotonic clocks (never wall-clock subtraction for durations):

- batch / document / phase / page / operation / attempt

Exposed elapsed fields:

- `batch_elapsed_seconds`
- `document_elapsed_seconds`
- `phase_elapsed_seconds`
- `page_elapsed_seconds`
- `operation_elapsed_seconds`
- `attempt_elapsed_seconds`

UI labels must not call document elapsed “Total elapsed”.

## Separate deadlines

- `document_deadline_remaining_seconds`
- `page_deadline_remaining_seconds`
- `operation_deadline_remaining_seconds`
- `attempt_deadline_remaining_seconds`

Legacy `deadline_remaining_seconds` is the most specific active deadline and is
deprecated. Missing deadlines are `null`.

On a new page: reset page and operation deadlines; retain document deadline.
On retry: reset attempt deadline; bump attempt number.

## Slow warning

Backend fields:

- `slow_warning_status`: inactive | approaching_threshold | active | resolved
- tied to `operation_id`, `attempt_number`, `document_page_number`,
  `worker_generation`

Changing any of those identities clears the prior warning. The UI must never
show “0 seconds elapsed” with an active OCR slow warning from a previous
operation.

## ETA

Backend remains authoritative. Estimates are route-class aware
(`digital_native`, embedded verification, targeted repair, full OCR
primary/fallback). Recalculate after routing, page terminal, fallback, retry,
cancellation, document completion, or queue change — not on display ticks.

Frontend shared ticker (`liveProgressClockStore`):

- one interval for the app
- snapshot + `received_at_monotonic` baseline
- display-only interpolation between snapshots
- remaining never negative; overdue → “Recalculating estimate…”
- hidden tabs pause display ticks only; SSE stays connected

See `phase-4.5-live-progress.md` and ADRs 0031–0033.
