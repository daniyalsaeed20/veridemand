import { Chip, Stack, Typography } from "@mui/material";

export interface VisualPageStatusProps {
  readonly status: string;
  readonly pagesCompleted: number;
  readonly pagesTotal: number;
  readonly sourcePolicy: string | null | undefined;
}

export function VisualPageStatus({
  status,
  pagesCompleted,
  pagesTotal,
  sourcePolicy,
}: VisualPageStatusProps) {
  return (
    <Stack
      direction="row"
      spacing={1}
      sx={{ alignItems: "center", flexWrap: "wrap" }}
      useFlexGap
      data-testid="visual-page-status"
    >
      <Chip size="small" label={status} />
      <Typography variant="body2">
        Pages {pagesCompleted}/{pagesTotal}
      </Typography>
      {sourcePolicy ? <Chip size="small" variant="outlined" label={sourcePolicy} /> : null}
    </Stack>
  );
}
