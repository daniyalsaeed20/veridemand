import { Stack, Typography } from "@mui/material";

interface QueueEstimateProps {
  readonly activeCount: number;
  readonly queuedCount: number;
  readonly completedCount: number;
  readonly remainingCount: number;
  readonly fairSchedulingEnabled?: boolean | null;
  readonly queueEtaLabel?: string | null;
}

export function QueueEstimate({
  activeCount,
  queuedCount,
  completedCount,
  remainingCount,
  fairSchedulingEnabled,
  queueEtaLabel,
}: QueueEstimateProps) {
  return (
    <Stack spacing={0.5} aria-label="Queue estimate">
      <Typography variant="body2" color="text.secondary">
        Active: {activeCount} · Queued: {queuedCount} · Completed: {completedCount} · Remaining:{" "}
        {remainingCount}
      </Typography>
      {queueEtaLabel ? (
        <Typography variant="body2" color="text.secondary">
          Estimated queue remaining: {queueEtaLabel}
        </Typography>
      ) : null}
      {fairSchedulingEnabled ? (
        <Typography variant="caption" color="text.secondary">
          Processing will rotate between large documents so smaller documents can finish sooner.
          Fair scheduling does not reduce total OCR computation.
        </Typography>
      ) : null}
    </Stack>
  );
}
