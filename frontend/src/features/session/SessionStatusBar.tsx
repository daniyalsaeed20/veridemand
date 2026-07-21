import RestartAltIcon from "@mui/icons-material/RestartAlt";
import WifiIcon from "@mui/icons-material/Wifi";
import WifiOffIcon from "@mui/icons-material/WifiOff";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Stack,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import type { SessionSnapshot, SessionStatus } from "../../contracts";
import { STATUS_TONE_COLOR, type StatusTone } from "../../app/theme";

const STATUS_LABEL: Record<SessionStatus, string> = {
  created: "Created",
  accepting_uploads: "Accepting uploads",
  queued: "Queued",
  processing: "Processing",
  ready: "Ready",
  reset: "Reset",
  expired: "Expired",
  failed: "Failed",
  deleted: "Deleted",
};

const STATUS_TONE: Record<SessionStatus, StatusTone> = {
  created: "neutral",
  accepting_uploads: "neutral",
  queued: "caution",
  processing: "caution",
  ready: "positive",
  reset: "neutral",
  expired: "critical",
  failed: "critical",
  deleted: "critical",
};

interface SessionStatusBarProps {
  readonly snapshot: SessionSnapshot;
  readonly connected: boolean;
  readonly reconnecting: boolean;
  readonly isResetting: boolean;
  readonly onReset: () => void;
}

function formatRemaining(seconds: number): string {
  if (seconds <= 0) {
    return "expired";
  }
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes <= 0) {
    return `${rest}s`;
  }
  return `${minutes}m ${rest.toString().padStart(2, "0")}s`;
}

export function SessionStatusBar({
  snapshot,
  connected,
  reconnecting,
  isResetting,
  onReset,
}: SessionStatusBarProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [remaining, setRemaining] = useState(snapshot.seconds_remaining);

  useEffect(() => {
    const expiresAtMs = new Date(snapshot.expires_at).getTime();
    const tick = () => {
      const secondsLeft = Math.max(0, Math.round((expiresAtMs - Date.now()) / 1000));
      setRemaining(secondsLeft);
    };
    tick();
    const interval = window.setInterval(tick, 1000);
    return () => window.clearInterval(interval);
  }, [snapshot.expires_at]);

  const handleConfirmReset = () => {
    setConfirmOpen(false);
    onReset();
  };

  return (
    <Card variant="outlined" data-testid="session-id" data-session-id={snapshot.session_id}>
      <CardContent>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          sx={{ justifyContent: "space-between", alignItems: { sm: "center" } }}
        >
          <Stack
            direction="row"
            spacing={1}
            sx={{ flexWrap: "wrap", gap: 1, alignItems: "center" }}
          >
            <Chip
              label={STATUS_LABEL[snapshot.status]}
              color={STATUS_TONE_COLOR[STATUS_TONE[snapshot.status]]}
              size="small"
            />
            <Chip
              icon={connected ? <WifiIcon /> : <WifiOffIcon />}
              label={connected ? "Live" : reconnecting ? "Reconnecting..." : "Offline"}
              color={connected ? "success" : reconnecting ? "warning" : "default"}
              size="small"
              variant="outlined"
            />
            <Chip
              label={`Expires in ${formatRemaining(remaining)}`}
              color={snapshot.expiring || remaining <= 60 ? "warning" : "default"}
              size="small"
              variant="outlined"
            />
          </Stack>

          <Box>
            <Button
              variant="outlined"
              color="error"
              size="small"
              startIcon={<RestartAltIcon />}
              disabled={isResetting}
              onClick={() => setConfirmOpen(true)}
            >
              {isResetting ? "Resetting..." : "Reset session"}
            </Button>
          </Box>
        </Stack>

        {snapshot.expiring ? (
          <Typography variant="body2" color="warning.main" sx={{ mt: 1 }}>
            This session is about to expire. Uploaded files and progress will be permanently
            removed.
          </Typography>
        ) : null}
      </CardContent>

      <Dialog open={confirmOpen} onClose={() => setConfirmOpen(false)}>
        <DialogTitle>Reset this session?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Resetting permanently deletes all uploaded files and queued work in this session and
            starts a fresh one. This cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOpen(false)}>Cancel</Button>
          <Button onClick={handleConfirmReset} color="error" variant="contained" autoFocus>
            Reset session
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
