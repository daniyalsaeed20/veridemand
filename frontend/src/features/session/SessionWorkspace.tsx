import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { Alert, AlertTitle, Box, Button, CircularProgress, Stack, Typography } from "@mui/material";

import { ApiError } from "../../api/http";
import { UploadPanel } from "../upload/UploadPanel";
import { QueueDashboard } from "../queue/QueueDashboard";
import { SessionStatusBar } from "./SessionStatusBar";
import { useRuntimeSession } from "./useRuntimeSession";
import { useSessionEvents } from "./useSessionEvents";

export function SessionWorkspace() {
  const session = useRuntimeSession();
  const events = useSessionEvents(session.sessionId, { onSessionGone: session.markGone });

  if (session.error && !session.snapshot) {
    const message =
      session.error instanceof ApiError
        ? session.error.message
        : "The workspace could not be started.";
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button color="inherit" size="small" onClick={() => void session.reset()}>
            Retry
          </Button>
        }
      >
        <AlertTitle>Could not start a session</AlertTitle>
        {message}
      </Alert>
    );
  }

  if (session.expired) {
    return (
      <Alert
        severity="warning"
        role="alert"
        action={
          <Button
            color="inherit"
            size="small"
            startIcon={<RestartAltIcon />}
            disabled={session.isResetting}
            onClick={() => void session.reset()}
          >
            Start new session
          </Button>
        }
      >
        <AlertTitle>Session ended</AlertTitle>
        This runtime session has expired or was closed. All uploaded files and progress have been
        permanently removed. Start a new session to continue.
      </Alert>
    );
  }

  if (!session.snapshot || session.sessionId === null) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", py: 8 }}>
        <Stack spacing={2} sx={{ alignItems: "center" }}>
          <CircularProgress />
          <Typography variant="body2" color="text.secondary">
            Starting a runtime session...
          </Typography>
        </Stack>
      </Box>
    );
  }

  const snapshot = session.snapshot;
  const interactionsDisabled =
    session.isResetting || snapshot.status === "expired" || snapshot.status === "deleted";

  return (
    <Stack spacing={3}>
      <SessionStatusBar
        snapshot={snapshot}
        connected={events.connected}
        reconnecting={events.reconnecting}
        isResetting={session.isResetting}
        onReset={() => void session.reset()}
      />
      <UploadPanel
        sessionId={session.sessionId}
        limits={snapshot.limits}
        disabled={interactionsDisabled}
      />
      <QueueDashboard
        sessionId={session.sessionId}
        snapshot={snapshot}
        disabled={interactionsDisabled}
      />
    </Stack>
  );
}
