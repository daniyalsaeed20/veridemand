# 0046 — Queue priority controls

## Status

Accepted

## Context

Users may want to prioritise a specific document in the processing queue.

## Decision

Three operations: move_ahead, move_behind, restore_default_priority. Changes
affect future turns only; the currently running page is never interrupted.
Priority changes are recorded with old/new values and effective next turn.
No pause/resume is implemented in this correction.

## Consequences

Users can influence scheduling order without disrupting active processing.
Controls are disabled for terminal documents and the currently active page.
