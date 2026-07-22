import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { Alert, AlertTitle, Box, Button, CircularProgress, Stack, Typography } from "@mui/material";

import { ApiError } from "../../api/http";
import { UploadPanel } from "../upload/UploadPanel";
import { QueueDashboard } from "../queue/QueueDashboard";
import { CanonicalViewer } from "../viewer/CanonicalViewer";
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

      {/* Two-column workspace: the queue panel (upload + documents) on the
          left, the canonical document viewer on the right. The viewer column
          renders its own empty state until a document is selected. */}
      <Stack direction={{ xs: "column", lg: "row" }} spacing={3} sx={{ alignItems: "stretch" }}>
        <Stack spacing={3} sx={{ flex: { lg: "0 0 420px" }, minWidth: 0 }}>
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

        <Box sx={{ flex: "1 1 auto", minWidth: 0 }}>
          <CanonicalViewer sessionId={session.sessionId} documents={snapshot.documents} />
        </Box>
      </Stack>
    </Stack>
  );
}
