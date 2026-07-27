import { Collapse, List, ListItem, ListItemText, Typography } from "@mui/material";
import { useMemo, useState } from "react";

interface TimelineEntry {
  readonly id: string;
  readonly label: string;
  readonly active?: boolean;
  readonly done?: boolean;
}

interface ProcessingTimelineProps {
  readonly entries: readonly TimelineEntry[];
  readonly stageTimeline?: readonly Record<string, unknown>[] | null;
}

const MAX_ROWS = 12;

function coalesceTimeline(
  stageTimeline: readonly Record<string, unknown>[] | null | undefined,
  fallback: readonly TimelineEntry[],
): TimelineEntry[] {
  if (!stageTimeline || stageTimeline.length === 0) {
    return [...fallback].slice(-MAX_ROWS);
  }
  const rows: TimelineEntry[] = [];
  for (const item of stageTimeline) {
    const op = typeof item.operation === "string" ? item.operation : "stage";
    const status = typeof item.status === "string" ? item.status : "";
    const elapsed =
      typeof item.elapsed_seconds === "number" ? ` — ${item.elapsed_seconds.toFixed(1)}s` : "";
    const isHeartbeat = status === "heartbeat";
    const label = `${op.replaceAll("_", " ")}${elapsed}`;
    if (isHeartbeat && rows.length > 0) {
      // Coalesce heartbeats into the current active row.
      const last = rows[rows.length - 1];
      rows[rows.length - 1] = { ...last, active: true, label: `${last.label.split(" — ")[0]}${elapsed}` };
      continue;
    }
    rows.push({
      id: `${op}-${rows.length}`,
      label,
      active: status === "started" || status === "running",
      done: status === "completed" || status === "skipped",
    });
  }
  return rows.slice(-MAX_ROWS);
}

export function ProcessingTimeline({ entries, stageTimeline }: ProcessingTimelineProps) {
  const [open, setOpen] = useState(false);
  const rows = useMemo(
    () => coalesceTimeline(stageTimeline, entries),
    [stageTimeline, entries],
  );

  return (
    <div>
      <Typography
        variant="body2"
        component="button"
        onClick={() => setOpen((v) => !v)}
        sx={{
          border: 0,
          background: "none",
          cursor: "pointer",
          p: 0,
          color: "primary.main",
          textAlign: "left",
        }}
        aria-expanded={open}
      >
        {open ? "Hide processing details" : "Show processing details"}
      </Typography>
      <Collapse in={open}>
        <List dense aria-label="Processing timeline" sx={{ py: 0.5 }}>
          {rows.map((row) => (
            <ListItem key={row.id} disableGutters sx={{ py: 0 }}>
              <ListItemText
                primary={`${row.done ? "✓" : row.active ? "→" : "○"} ${row.label}`}
                slotProps={{
                  primary: { variant: "body2", color: "text.secondary" },
                }}
              />
            </ListItem>
          ))}
        </List>
      </Collapse>
    </div>
  );
}
