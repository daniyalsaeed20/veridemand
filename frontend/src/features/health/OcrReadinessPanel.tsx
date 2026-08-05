import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import RefreshIcon from "@mui/icons-material/Refresh";
import WifiFindIcon from "@mui/icons-material/WifiFind";
import {
  Alert,
  AlertTitle,
  Box,
  Button,
  Collapse,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import type { OcrRuntimeStatus, ReadinessResponse } from "../../contracts";
import { retryOcrRuntime } from "./ocrRuntimeApi";
import { deriveOcrPanelMode, type OcrReadinessPanelMode } from "./ocrReadinessMode";
import { healthQueryKeys, isOcrStarting } from "./useHealth";

interface OcrReadinessPanelProps {
  readonly readiness: ReadinessResponse | undefined;
  readonly readinessError: boolean;
  readonly onCheckConnection: () => void;
}

function elapsedSeconds(startedAt: string | null | undefined, nowMs: number): number {
  if (!startedAt) {
    return 0;
  }
  const started = Date.parse(startedAt);
  if (Number.isNaN(started)) {
    return 0;
  }
  return Math.max(0, Math.floor((nowMs - started) / 1000));
}

function buildDiagnostics(
  ocr: OcrRuntimeStatus | null | undefined,
  mode: OcrReadinessPanelMode,
  buildIdentity?: { git_commit?: string | null; application_version?: string },
): string {
  const lines = [
    "VeriDemand OCR diagnostics",
    `mode: ${mode}`,
    `state: ${ocr?.state ?? "unknown"}`,
    `stage: ${ocr?.stage ?? "n/a"}`,
    `error_code: ${ocr?.error_code ?? (mode === "backend_unreachable" ? "backend_unreachable" : "n/a")}`,
    `attempt_number: ${ocr?.attempt_number ?? "n/a"}`,
    `attempt_id: ${ocr?.attempt_id ?? "n/a"}`,
    `attempt_started_at: ${ocr?.attempt_started_at ?? "n/a"}`,
    `last_transition_at: ${ocr?.last_transition_at ?? "n/a"}`,
    `retryable: ${ocr?.retryable ?? "n/a"}`,
    `model_verification_status: ${ocr?.model_verification_status ?? "n/a"}`,
    `detector_status: ${ocr?.detector_status ?? "n/a"}`,
    `recognizer_status: ${ocr?.recognizer_status ?? "n/a"}`,
    `technical_detail: ${ocr?.technical_detail ?? "n/a"}`,
    `application_version: ${buildIdentity?.application_version ?? "n/a"}`,
    `git_commit: ${buildIdentity?.git_commit ?? "n/a"}`,
  ];
  return lines.join("\n");
}

export function OcrReadinessPanel({
  readiness,
  readinessError,
  onCheckConnection,
}: OcrReadinessPanelProps) {
  const queryClient = useQueryClient();
  const ocr = readiness?.ocr_runtime ?? null;
  const mode = deriveOcrPanelMode(readiness, readinessError);
  const [showDetails, setShowDetails] = useState(false);
  const [copied, setCopied] = useState(false);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [showReadyFlash, setShowReadyFlash] = useState(false);

  useEffect(() => {
    if (mode !== "starting") {
      return;
    }
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [mode]);

  useEffect(() => {
    if (mode === "ready_flash") {
      setShowReadyFlash(true);
      const id = window.setTimeout(() => setShowReadyFlash(false), 2500);
      return () => window.clearTimeout(id);
    }
    setShowReadyFlash(false);
    return undefined;
  }, [mode, ocr?.attempt_id]);

  const retry = useMutation({
    mutationFn: () => retryOcrRuntime(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: healthQueryKeys.readiness });
    },
  });

  const diagnostics = useMemo(
    () =>
      buildDiagnostics(ocr, mode, {
        git_commit: readiness?.git_commit,
        application_version: readiness?.application_version,
      }),
    [ocr, mode, readiness?.git_commit, readiness?.application_version],
  );

  if (mode === "hidden" || (mode === "ready_flash" && !showReadyFlash)) {
    return null;
  }

  if (mode === "ready_flash" && showReadyFlash) {
    return (
      <Alert severity="success" role="status">
        <AlertTitle>Printed OCR is ready</AlertTitle>
      </Alert>
    );
  }

  if (mode === "starting") {
    const elapsed = elapsedSeconds(ocr?.attempt_started_at ?? undefined, nowMs);
    const stageLabel = ocr?.stage_label ?? "Starting printed OCR…";
    const step = ocr?.stage_index;
    const total = ocr?.stage_count ?? 5;
    return (
      <Alert severity="info" role="status">
        <AlertTitle>Printed OCR is starting</AlertTitle>
        <Stack spacing={1}>
          <Typography variant="body2">{stageLabel}</Typography>
          <Typography variant="body2" color="text.secondary">
            {step != null ? `Step ${step} of ${total}` : `Up to ${total} steps`}
            {" · "}
            {elapsed} second{elapsed === 1 ? "" : "s"} elapsed
            {ocr?.attempt_number ? ` · Attempt ${ocr.attempt_number}` : ""}
          </Typography>
          <LinearProgress aria-label="OCR startup progress" />
        </Stack>
      </Alert>
    );
  }

  if (mode === "disabled") {
    return (
      <Alert severity="warning" role="status">
        <AlertTitle>Printed OCR is disabled</AlertTitle>
        {ocr?.user_message ?? "Printed OCR is disabled."}
        {ocr?.operator_hint ? (
          <Typography variant="body2" sx={{ mt: 1 }}>
            Suggested action: {ocr.operator_hint}
          </Typography>
        ) : null}
      </Alert>
    );
  }

  if (mode === "backend_unreachable") {
    return (
      <Alert
        severity="error"
        role="alert"
        action={
          <Button
            color="inherit"
            size="small"
            startIcon={<WifiFindIcon />}
            onClick={onCheckConnection}
          >
            Check connection
          </Button>
        }
      >
        <AlertTitle>Backend connection unavailable</AlertTitle>
        The web interface cannot reach the VeriDemand backend.
      </Alert>
    );
  }

  const retryable = mode === "failed_retryable";
  return (
    <Alert severity="error" role="alert">
      <AlertTitle>Printed OCR could not start</AlertTitle>
      <Stack spacing={1.5}>
        <Typography variant="body2">
          {ocr?.user_message ?? "Printed OCR could not start."}
        </Typography>
        {ocr?.operator_hint ? (
          <Typography variant="body2">Suggested action: {ocr.operator_hint}</Typography>
        ) : null}
        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
          {retryable ? (
            <Button
              size="small"
              variant="contained"
              color="inherit"
              startIcon={<RefreshIcon />}
              disabled={retry.isPending || isOcrStarting(ocr)}
              onClick={() => retry.mutate()}
            >
              {retry.isPending ? "Retrying…" : "Retry OCR"}
            </Button>
          ) : (
            <Typography variant="caption" color="text.secondary">
              Retry OCR is unavailable until the underlying configuration or model issue is fixed.
            </Typography>
          )}
          <Button size="small" color="inherit" onClick={() => setShowDetails((v) => !v)}>
            {showDetails ? "Hide technical details" : "Show technical details"}
          </Button>
          <Button
            size="small"
            color="inherit"
            startIcon={<ContentCopyIcon />}
            onClick={() => {
              void navigator.clipboard.writeText(diagnostics).then(() => {
                setCopied(true);
                window.setTimeout(() => setCopied(false), 1500);
              });
            }}
          >
            {copied ? "Copied" : "Copy diagnostics"}
          </Button>
        </Stack>
        <Collapse in={showDetails}>
          <Box
            component="pre"
            sx={{
              m: 0,
              p: 1,
              bgcolor: "action.hover",
              borderRadius: 1,
              fontSize: 12,
              overflow: "auto",
            }}
          >
            {diagnostics}
          </Box>
        </Collapse>
      </Stack>
    </Alert>
  );
}
