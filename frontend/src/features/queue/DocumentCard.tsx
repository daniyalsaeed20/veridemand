import CancelIcon from "@mui/icons-material/Cancel";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { Box, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { STATUS_TONE_COLOR, type StatusTone } from "../../app/theme";
import { formatBytes } from "../upload/clientChecks";
import { processDocuments } from "../session/sessionApi";
import { sessionKeys } from "../session/sessionKeys";
import { useViewerStore } from "../viewer/viewerState";
import type {
  CanonicalisationMethod,
  CanonicalStatus,
  DocumentStatus,
  DocumentSummary,
} from "../viewer/viewerApi";
import { cancelDocument, removeDocument } from "./documentApi";

const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  canonicalising: "Canonicalising",
  ready_for_extraction: "Ready for extraction",
  inspecting_native: "Inspecting native text",
  extracting_native: "Extracting native text",
  native_trust_complete: "Native trust complete",
  cancelled: "Cancelled",
  failed: "Failed",
};

const STATUS_TONE: Record<DocumentStatus, StatusTone> = {
  uploaded: "neutral",
  queued: "caution",
  canonicalising: "caution",
  ready_for_extraction: "positive",
  inspecting_native: "caution",
  extracting_native: "caution",
  native_trust_complete: "positive",
  cancelled: "neutral",
  failed: "critical",
};

const CANONICAL_STATUS_LABEL: Record<CanonicalStatus, string> = {
  pending: "Pending",
  queued: "Queued",
  canonicalising: "Canonicalising",
  ready: "Ready",
  failed: "Failed",
  cancelled: "Cancelled",
};

const CANONICALISATION_METHOD_LABEL: Record<CanonicalisationMethod, string> = {
  original_pdf: "Original PDF",
  libreoffice_writer_pdf: "LibreOffice conversion",
  reportlab_text_pdf: "Text rendering",
  reportlab_image_pdf: "Image rendering",
};

interface DocumentCardProps {
  readonly sessionId: string;
  readonly document: DocumentSummary;
  readonly disabled?: boolean;
}

export function DocumentCard({ sessionId, document, disabled = false }: DocumentCardProps) {
  const queryClient = useQueryClient();
  const selectDocument = useViewerStore((state) => state.selectDocument);
  const selectedDocumentId = useViewerStore((state) => state.selectedDocumentId);

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
  const canCancel =
    document.status === "queued" ||
    document.status === "canonicalising" ||
    document.status === "inspecting_native" ||
    document.status === "extracting_native";
  const canRemove =
    document.status === "uploaded" ||
    document.status === "ready_for_extraction" ||
    document.status === "native_trust_complete" ||
    document.status === "cancelled" ||
    document.status === "failed";
  const isSelected = selectedDocumentId === document.document_id;

  const pageLabel =
    document.page_count_status === "known" && document.page_count != null
      ? `${document.page_count} page${document.page_count === 1 ? "" : "s"}`
      : "Pages pending";

  const hasCanonicalInfo =
    document.canonical_status != null ||
    document.canonicalisation_method != null ||
    document.canonical_view_available;

  return (
    <Paper variant="outlined" sx={{ p: 2, borderColor: isSelected ? "primary.main" : undefined }}>
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
              {document.format.toUpperCase()} · {pageLabel} · {formatBytes(document.size_bytes)}
              {document.queue_position != null ? ` · position ${document.queue_position}` : ""}
            </Typography>
          </Box>
          <Chip
            label={STATUS_LABEL[document.status]}
            color={STATUS_TONE_COLOR[STATUS_TONE[document.status]]}
            size="small"
          />
        </Stack>

        {document.status === "queued" ||
        document.status === "canonicalising" ||
        document.status === "inspecting_native" ||
        document.status === "extracting_native" ? (
          <Box>
            <LinearProgress
              variant="determinate"
              value={document.progress_percent}
              aria-label="Document processing progress"
            />
            <Typography variant="caption" color="text.secondary">
              {document.status === "canonicalising"
                ? "Canonicalising for the viewer — no extraction has been performed yet."
                : "Inspecting native PDF text — progress is capped at 35% until visual processing."}
            </Typography>
          </Box>
        ) : null}

        {document.status === "ready_for_extraction" ? (
          <Typography variant="caption" color="text.secondary">
            {document.canonical_view_available
              ? "Canonical document ready. Extraction has not started."
              : "Extraction has not started. No results are available yet."}
          </Typography>
        ) : null}

        {document.status === "native_trust_complete" ? (
          <Typography variant="caption" color="text.secondary">
            Native trust inspection complete. Visual agreement and processing have not started.
          </Typography>
        ) : null}

        {document.user_status_message ? (
          <Typography variant="caption" color="text.secondary">
            {document.user_status_message}
          </Typography>
        ) : null}

        {hasCanonicalInfo ? (
          <Typography variant="caption" color="text.secondary">
            Canonical:{" "}
            {document.canonical_status != null
              ? CANONICAL_STATUS_LABEL[document.canonical_status]
              : "—"}
            {document.canonicalisation_method != null
              ? ` · ${CANONICALISATION_METHOD_LABEL[document.canonicalisation_method]}`
              : ""}
            {document.page_count_status === "known" && document.page_count != null
              ? ` · ${document.page_count} page${document.page_count === 1 ? "" : "s"}`
              : ""}
            {` · ${formatBytes(document.size_bytes)}`}
          </Typography>
        ) : null}

        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
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
          {document.canonical_view_available ? (
            <Button
              size="small"
              variant={isSelected ? "contained" : "outlined"}
              startIcon={<OpenInNewIcon />}
              disabled={disabled}
              aria-pressed={isSelected}
              onClick={() => selectDocument(document.document_id)}
            >
              Open canonical document
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
