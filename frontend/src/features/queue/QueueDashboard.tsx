import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { processDocuments } from "../session/sessionApi";
import { sessionKeys } from "../session/sessionKeys";
import type { SessionSnapshot } from "../viewer/viewerApi";
import { DocumentCard } from "./DocumentCard";

interface QueueDashboardProps {
  readonly sessionId: string;
  readonly snapshot: SessionSnapshot;
  readonly disabled?: boolean;
  /** When true, Process actions are disabled (OCR worker / readiness gate). */
  readonly processBlocked?: boolean;
  readonly processBlockedReason?: string;
}

export function QueueDashboard({
  sessionId,
  snapshot,
  disabled = false,
  processBlocked = false,
  processBlockedReason,
}: QueueDashboardProps) {
  const queryClient = useQueryClient();
  const { counts, queue, documents } = snapshot;

  const processAll = useMutation({
    mutationFn: () => processDocuments(sessionId, null),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) }),
  });

  const hasQueueable = (counts.uploaded ?? 0) > 0;
  const processingDisabled = disabled || processBlocked;

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Stack
            direction="row"
            spacing={1}
            sx={{ justifyContent: "space-between", alignItems: "center" }}
          >
            <Typography variant="h2" component="h2">
              Documents &amp; queue
            </Typography>
            <Button
              variant="contained"
              size="small"
              startIcon={<PlayArrowIcon />}
              disabled={processingDisabled || !hasQueueable || processAll.isPending}
              onClick={() => processAll.mutate()}
            >
              {processAll.isPending ? "Queuing..." : "Process all uploaded"}
            </Button>
          </Stack>

          {processBlocked ? (
            <Alert severity="warning" role="status">
              {processBlockedReason ??
                "Printed OCR is still starting or unavailable. Check runtime readiness."}
            </Alert>
          ) : null}

          <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
            <CountChip label="Uploaded" value={counts.uploaded ?? 0} />
            <CountChip label="Queued" value={counts.queued ?? 0} />
            <CountChip label="Canonicalising" value={counts.canonicalising ?? 0} />
            <CountChip label="Ready" value={counts.ready_for_extraction ?? 0} />
            <CountChip label="Cancelled" value={counts.cancelled ?? 0} />
            <CountChip label="Failed" value={counts.failed ?? 0} />
          </Stack>

          <Typography variant="body2" color="text.secondary">
            Queue: {queue.pending} pending · {queue.running} running · single-worker, first-in
            first-out. Printed OCR progress is capped at 65% in this phase.
          </Typography>

          <Divider />

          {documents.length === 0 ? (
            <Box sx={{ py: 3, textAlign: "center" }}>
              <Typography variant="body2" color="text.secondary">
                No documents yet. Upload files to build the queue.
              </Typography>
            </Box>
          ) : (
            <Stack spacing={1.5}>
              {documents.map((document) => (
                <DocumentCard
                  key={document.document_id}
                  sessionId={sessionId}
                  document={document}
                  disabled={disabled}
                  processBlocked={processBlocked}
                />
              ))}
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
}

function CountChip({ label, value }: { label: string; value: number }) {
  return (
    <Chip
      label={`${label}: ${value}`}
      size="small"
      variant={value > 0 ? "filled" : "outlined"}
      color={value > 0 ? "primary" : "default"}
    />
  );
}
