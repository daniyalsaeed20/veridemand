import { Chip, Stack, Typography } from "@mui/material";

export interface VisualPageStatusProps {
  readonly status: string;
  readonly pagesCompleted: number;
  readonly pagesTotal: number;
  readonly sourcePolicy: string | null | undefined;
  readonly phase3Policy?: string | null;
  readonly embeddedVerified?: number | null;
  readonly fullOcrSelected?: number | null;
  readonly fullOcrCompleted?: number | null;
}

export function VisualPageStatus({
  status,
  pagesCompleted,
  pagesTotal,
  sourcePolicy,
  phase3Policy,
  embeddedVerified,
  fullOcrSelected,
  fullOcrCompleted,
}: VisualPageStatusProps) {
  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{ alignItems: "center", flexWrap: "wrap" }}
      useFlexGap
      data-testid="visual-page-status"
    >
      <Chip size="small" label={status} data-testid="visual-processing-status-chip" />
      <Typography variant="body2" data-testid="visual-pages-progress">
        Document pages completed {pagesCompleted}
        {pagesTotal > 0 ? ` of ${pagesTotal}` : ""}
      </Typography>
      {sourcePolicy ? (
        <Chip
          size="small"
          variant="outlined"
          label={`Phase 4: ${sourcePolicy}`}
          data-testid="phase4-policy-chip"
        />
      ) : null}
      {phase3Policy ? (
        <Chip
          size="small"
          variant="outlined"
          label={`Phase 3 provisional: ${phase3Policy}`}
          data-testid="phase3-policy-chip"
        />
      ) : null}
      {embeddedVerified != null ? (
        <Typography variant="caption">Embedded verified: {embeddedVerified}</Typography>
      ) : null}
      {fullOcrSelected != null ? (
        <Typography variant="caption">
          Full OCR: {fullOcrCompleted ?? 0}/{fullOcrSelected}
        </Typography>
      ) : null}
    </Stack>
  );
}
