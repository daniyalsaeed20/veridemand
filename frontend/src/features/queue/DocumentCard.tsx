import CancelIcon from "@mui/icons-material/Cancel";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { Box, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { DocumentStatus, DocumentSummary } from "../../contracts";
import { STATUS_TONE_COLOR, type StatusTone } from "../../app/theme";
import { processDocuments } from "../session/sessionApi";
import { sessionKeys } from "../session/sessionKeys";
import { cancelDocument, removeDocument } from "./documentApi";

const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  preparing: "Preparing",
  ready_for_extraction: "Ready for extraction",
  cancelled: "Cancelled",
  failed: "Failed",
};

const STATUS_TONE: Record<DocumentStatus, StatusTone> = {
  uploaded: "neutral",
  queued: "caution",
  preparing: "caution",
  ready_for_extraction: "positive",
  cancelled: "neutral",
  failed: "critical",
};

interface DocumentCardProps {
  readonly sessionId: string;
  readonly document: DocumentSummary;
  readonly disabled?: boolean;
}

export function DocumentCard({ sessionId, document, disabled = false }: DocumentCardProps) {
  const queryClient = useQueryClient();

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: sessionKeys.detail(sessionId) });

  const processMutation = useMutation({
    mutationFn: () => processDocuments(sessionId, [document.document_id]),
    onSuccess: invalidate,
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelDocument(sessionId, document.document_id),
    onSuccess: invalidate,
  });
  const removeMutation = useMutation({
    mutationFn: () => removeDocument(sessionId, document.document_id),
    onSuccess: invalidate,
  });

  const busy =
    disabled || processMutation.isPending || cancelMutation.isPending || removeMutation.isPending;

  const canProcess = document.status === "uploaded";
  const canCancel = document.status === "queued" || document.status === "preparing";
  const canRemove =
    document.status === "uploaded" ||
    document.status === "ready_for_extraction" ||
    document.status === "cancelled" ||
    document.status === "failed";

  const pageLabel =
    document.page_count_status === "known" && document.page_count != null
      ? `${document.page_count} page${document.page_count === 1 ? "" : "s"}`
      : "Pages pending";

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack spacing={1.5}>
        <Stack
          direction="row"
          spacing={1}
          sx={{ justifyContent: "space-between", alignItems: "flex-start" }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="body1" sx={{ fontWeight: 600, wordBreak: "break-word" }}>
              {document.display_filename}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {document.format.toUpperCase()} · {pageLabel}
              {document.queue_position != null ? ` · position ${document.queue_position}` : ""}
            </Typography>
          </Box>
          <Chip
            label={STATUS_LABEL[document.status]}
            color={STATUS_TONE_COLOR[STATUS_TONE[document.status]]}
            size="small"
          />
        </Stack>

        {document.status === "queued" || document.status === "preparing" ? (
          <Box>
            <LinearProgress
              variant="determinate"
              value={document.progress_percent}
              aria-label="Preparation progress"
            />
            <Typography variant="caption" color="text.secondary">
              Preparing for extraction — no extraction has been performed yet.
            </Typography>
          </Box>
        ) : null}

        {document.status === "ready_for_extraction" ? (
          <Typography variant="caption" color="text.secondary">
            Prepared and ready for extraction. Extraction is not part of this phase; no results are
            available yet.
          </Typography>
        ) : null}

        <Stack direction="row" spacing={1}>
          {canProcess ? (
            <Button
              size="small"
              variant="contained"
              startIcon={<PlayArrowIcon />}
              disabled={busy}
              onClick={() => processMutation.mutate()}
            >
              Process
            </Button>
          ) : null}
          {canCancel ? (
            <Button
              size="small"
              variant="outlined"
              color="warning"
              startIcon={<CancelIcon />}
              disabled={busy}
              onClick={() => cancelMutation.mutate()}
            >
              Cancel
            </Button>
          ) : null}
          {canRemove ? (
            <Button
              size="small"
              variant="outlined"
              color="error"
              startIcon={<DeleteOutlineIcon />}
              disabled={busy}
              onClick={() => removeMutation.mutate()}
            >
              Remove
            </Button>
          ) : null}
        </Stack>
      </Stack>
    </Paper>
  );
}
