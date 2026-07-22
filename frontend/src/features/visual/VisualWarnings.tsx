import { Alert, Stack } from "@mui/material";

export interface VisualWarningsProps {
  readonly warnings: readonly { code: string; message: string }[];
}

export function VisualWarnings({ warnings }: VisualWarningsProps) {
  if (warnings.length === 0) {
    return null;
  }
  return (
    <Stack spacing={1} data-testid="visual-warnings">
      {warnings.map((warning) => (
        <Alert key={`${warning.code}-${warning.message}`} severity="warning">
          {warning.message}
        </Alert>
      ))}
    </Stack>
  );
}
