import { Alert, AlertTitle } from "@mui/material";

export const RUNTIME_WARNING_TEXT =
  "VeriDemand is currently runtime-only. Refreshing, closing, or resetting this page may " +
  "permanently remove all uploaded files and extracted results from this session.";

export function RuntimeWarning() {
  return (
    <Alert severity="warning" variant="outlined" role="alert">
      <AlertTitle>Runtime-only session</AlertTitle>
      {RUNTIME_WARNING_TEXT}
    </Alert>
  );
}
