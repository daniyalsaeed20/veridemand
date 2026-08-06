import RefreshIcon from "@mui/icons-material/Refresh";
import { Button, Card, CardContent, Chip, Divider, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

import { environment } from "../../api/environment";
import { STATUS_TONE_COLOR, type StatusTone } from "../../app/theme";
import type { ReadinessResponse } from "../../contracts";
import { useLiveness, useReadiness } from "./useHealth";

const READINESS_LABEL: Record<ReadinessResponse["status"], string> = {
  ready: "Ready",
  degraded: "Degraded",
  not_ready: "Not ready",
};

const READINESS_TONE: Record<ReadinessResponse["status"], StatusTone> = {
  ready: "positive",
  degraded: "caution",
  not_ready: "critical",
};

function StatusRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Stack
      direction="row"
      spacing={2}
      sx={{ justifyContent: "space-between", alignItems: "center", py: 0.5 }}
    >
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      {children}
    </Stack>
  );
}

function formatTimestamp(timestamp: string | undefined): string {
  if (!timestamp) {
    return "-";
  }
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString();
}

export function HealthStatusCard() {
  const liveness = useLiveness();
  const readiness = useReadiness();

  const processTone: StatusTone = liveness.isSuccess
    ? "positive"
    : liveness.isPending
      ? "neutral"
      : "critical";
  const processLabel = liveness.isSuccess
    ? "Live"
    : liveness.isPending
      ? "Checking..."
      : "Unavailable";

  let readinessTone: StatusTone = "neutral";
  let readinessLabel = "Checking...";
  if (readiness.isSuccess) {
    readinessTone = READINESS_TONE[readiness.data.status];
    readinessLabel = READINESS_LABEL[readiness.data.status];
  } else if (readiness.isError) {
    readinessTone = "critical";
    readinessLabel = "Unavailable";
  }

  const requestId = liveness.data?.request_id ?? "-";
  const lastChecked = formatTimestamp(liveness.data?.timestamp);
  const isChecking = liveness.isFetching || readiness.isFetching;

  const handleRetry = () => {
    void liveness.refetch();
    void readiness.refetch();
  };

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack
          direction="row"
          sx={{ justifyContent: "space-between", alignItems: "center", mb: 1 }}
        >
          <Typography variant="h2" component="h2">
            Backend health
          </Typography>
          <Button
            size="small"
            variant="outlined"
            startIcon={<RefreshIcon />}
            onClick={handleRetry}
            disabled={isChecking}
            aria-label="Retry health checks"
          >
            Retry
          </Button>
        </Stack>

        <Divider sx={{ mb: 1 }} />

        <StatusRow label="Backend process">
          <Chip
            label={processLabel}
            color={STATUS_TONE_COLOR[processTone]}
            size="small"
            variant="filled"
          />
        </StatusRow>
        <StatusRow label="Backend readiness">
          <Chip
            label={readinessLabel}
            color={STATUS_TONE_COLOR[readinessTone]}
            size="small"
            variant="filled"
          />
        </StatusRow>
        <StatusRow label="Backend URL">
          <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
            {environment.apiBaseUrl}
          </Typography>
        </StatusRow>
        <StatusRow label="Configuration profile">
          <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
            {liveness.data?.configuration_profile ?? readiness.data?.configuration_profile ?? "-"}
          </Typography>
        </StatusRow>
        <StatusRow label="Phase 5 page-vision">
          <Typography variant="body2">
            {(
              liveness.data?.configuration_profile ??
              readiness.data?.configuration_profile ??
              ""
            ).includes("page_vision_on")
              ? "Conservative reservation ON (pnpm dev:phase5)"
              : "Off (pnpm dev:ocr / release default)"}
          </Typography>
        </StatusRow>
        <StatusRow label="Last successful check">
          <Typography variant="body2">{lastChecked}</Typography>
        </StatusRow>
        <StatusRow label="Request ID">
          <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
            {requestId}
          </Typography>
        </StatusRow>
      </CardContent>
    </Card>
  );
}
