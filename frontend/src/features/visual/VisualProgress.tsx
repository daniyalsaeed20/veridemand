import { Box, LinearProgress, Typography } from "@mui/material";

import type { VisualDocumentSummary } from "../../contracts";

export interface VisualProgressProps {
  readonly summary: VisualDocumentSummary;
}

export function VisualProgress({ summary }: VisualProgressProps) {
  const percent = summary.progress?.percent ?? 0;
  return (
    <Box>
      <LinearProgress variant="determinate" value={percent} aria-label="Visual OCR progress" />
      <Typography variant="caption" color="text.secondary">
        Visual OCR {percent}% · selected {summary.pages_selected} · completed{" "}
        {summary.pages_completed}/{summary.page_count}
      </Typography>
    </Box>
  );
}
