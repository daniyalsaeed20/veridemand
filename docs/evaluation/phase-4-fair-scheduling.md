# Fair scheduling evaluation (Correction 7)

## Interim architecture note

Correction 7 now implements **page-quantum heavy OCR** via `_heavy_consumer_loop`.
Synthetic acceptance must show a small document receiving a turn before a large
document finishes all selected heavy pages.

## Fairness metrics

| Metric | Measurement |
|---|---|
| Time to first processing turn | Wall clock from admission to first scheduler turn |
| Time to first completed page | Wall clock from admission to first page publication |
| Time to document completion | Wall clock from admission to terminal state |
| Maximum wait between turns | Longest interval a ready document waited |
| Average wait between turns | Mean interval between consecutive turns |
| Turn count | Total scheduler turns per document |
| Pages per turn | Average pages completed per scheduler turn |
| Starvation count | Documents that waited beyond aging threshold |
| Priority-aging activations | Number of aging adjustments applied |
| Worker idle time | Time OCR worker had no work |
| Model reload count | Expected: 1 (initial load only) |
| Worker restart count | Expected: 0 unless real failure |
| Total batch duration | Wall clock for entire batch |
| Per-document duration | Individual document completion times |

## Success criteria

- Smaller documents finish earlier relative to their work
- Large documents continue to progress (no indefinite starvation)
- No material increase in total batch time
- No model reload when switching documents
- No page processed twice
- No starvation detected

## Synthetic workloads

| ID | Description | Expected outcome |
|---|---|---|
| A | 12-page OCR + 2-page OCR | Small receives turn before large finishes |
| B | Native-only behind OCR | Native completes without joining heavy queue |
| C | Three equal OCR documents | Deterministic round-robin, no starvation |
| D | Continual small arrivals + one large | Aging ensures large progresses |
| E | 7 native + 2 OCR (billing) | Only 2 units in heavy queue |
| F | Many verified + 2 OCR (embedded) | Only 2 heavy units |
| G | Targeted repair + full OCR | Both receive fair turns |
| H | Cancellation while ready | Clean removal, no worker call |
| I | Cancellation while running | Safe cleanup, no partial page |
| J | Worker loss and retry | Affected page retries, others continue |
| K | Priority move-ahead/behind | Next turn reflects change |
| L | Shutdown with pending work | Clean cancellation, no orphans |
