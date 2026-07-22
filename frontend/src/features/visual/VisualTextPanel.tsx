import { Stack, Typography } from "@mui/material";

import type { VisualPageResult } from "../../contracts";

export interface VisualTextPanelProps {
  readonly page: VisualPageResult;
}

export function VisualTextPanel({ page }: VisualTextPanelProps) {
  const lines = page.lines ?? [];
  if (page.status === "completed_no_text") {
    return (
      <Typography variant="body2" data-testid="visual-no-text">
        No printed text was detected.
      </Typography>
    );
  }
  if (!page.visual_result_available || lines.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No OCR lines available for this page.
      </Typography>
    );
  }
  const orderedIds = page.reading_order?.line_ids ?? lines.map((line) => line.id);
  const byId = new Map(lines.map((line) => [line.id, line]));
  return (
    <Stack spacing={0.5} data-testid="visual-text-panel">
      <Typography variant="caption" color="text.secondary">
        Initial visual reading order — not final
      </Typography>
      {orderedIds.map((id) => {
        const line = byId.get(id);
        if (!line) {
          return null;
        }
        return (
          <Typography key={line.id} variant="body2" component="div">
            {line.normalised_text}
          </Typography>
        );
      })}
    </Stack>
  );
}
