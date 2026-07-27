import CancelIcon from "@mui/icons-material/Cancel";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { Box, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

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
import { applyMonotonicProgress, type ProgressFloor } from "./monotonicProgress";
import { ProcessingDetailsCard } from "../progress/ProcessingDetailsCard";
import { isProgressActive } from "../progress/deriveLiveProgress";

const STATUS_LABEL: Record<DocumentStatus, string> = {
  uploaded: "Uploaded",
  queued: "Queued",
  canonicalising: "Canonicalising",
  ready_for_extraction: "Ready for extraction",
  inspecting_native: "Inspecting native text",
  extracting_native: "Extracting native text",
  native_trust_complete: "Native trust complete",
  visual_pending: "Visual OCR pending",
  visual_processing: "Printed OCR running",
  visual_processing_complete: "Printed OCR complete",
  visual_processing_partial: "Printed OCR partial",
  visual_processing_failed: "Printed OCR failed",
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
  visual_pending: "caution",
  visual_processing: "caution",
  visual_processing_complete: "positive",
  visual_processing_partial: "caution",
  visual_processing_failed: "critical",
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
  readonly processBlocked?: boolean;
}

export function DocumentCard({
  sessionId,
  document: rawDocument,
  disabled = false,
  processBlocked = false,
}: DocumentCardProps) {
  const queryClient = useQueryClient();
  const selectDocument = useViewerStore((state) => state.selectDocument);
  const selectedDocumentId = useViewerStore((state) => state.selectedDocumentId);
  const floorRef = useRef<ProgressFloor | undefined>(undefined);
  const { document, floor } = applyMonotonicProgress(rawDocument, floorRef.current);
  floorRef.current = floor;

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
    disabled ||
    processBlocked ||
    processMutation.isPending ||
    cancelMutation.isPending ||
    removeMutation.isPending;

  const canProcess = document.status === "uploaded";
  const canCancel =
    document.status === "queued" ||
    document.status === "canonicalising" ||
    document.status === "inspecting_native" ||
    document.status === "extracting_native" ||
    document.status === "visual_pending" ||
    document.status === "visual_processing";
  const canRemove =
    document.status === "uploaded" ||
    document.status === "ready_for_extraction" ||
    document.status === "native_trust_complete" ||
    document.status === "visual_processing_complete" ||
    document.status === "visual_processing_partial" ||
    document.status === "visual_processing_failed" ||
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

        {isProgressActive(document.status) ? (
          <Box>
            <LinearProgress
              variant={document.progress_kind === "indeterminate" ? "indeterminate" : "determinate"}
              value={document.progress_percent}
              aria-label="Document processing progress"
            />
            <Box sx={{ mt: 0.75 }}>
              <ProcessingDetailsCard snapshot={document} />
            </Box>
            {document.user_status_message ? (
              <Typography variant="caption" color="text.secondary">
                {document.user_status_message}
              </Typography>
            ) : null}
            {document.attempt_number != null && document.max_attempts != null ? (
              <Typography variant="caption" color="text.secondary">
                Worker attempt: {document.attempt_number} of {document.max_attempts}
                {document.worker_generation != null
                  ? ` · Generation ${document.worker_generation}`
                  : ""}
              </Typography>
            ) : null}
            {document.progress_kind === "indeterminate" &&
            document.document_elapsed_seconds != null &&
            document.document_elapsed_seconds > 30 ? (
              <Typography variant="caption" color="warning.main">
                OCR is taking longer than expected. The backend timeout remains active.
              </Typography>
            ) : null}
          </Box>
        ) : null}

        {document.status === "ready_for_extraction" ? (
          <Typography variant="caption" color="text.secondary">
            {document.canonical_view_available
              ? "Canonical document ready. Extraction has not started."
              : "Extraction has not started. No results are available yet."}
          </Typography>
        ) : null}

        {document.status === "visual_processing_complete" ||
        document.status === "visual_processing_partial" ? (
          <Typography variant="caption" color="text.secondary">
            Printed visual OCR complete. Handwriting and final document structure have not been
            evaluated.
          </Typography>
        ) : null}

        {document.status === "visual_processing_failed" ? (
          <Stack spacing={0.5}>
            <Typography variant="caption" color="error.main">
              Visual OCR could not complete.
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Failed operation:{" "}
              {(document.failure_stage ?? document.current_operation ?? "paddle_ocr_pipeline")
                .replaceAll("_", " ")
                .replace("paddle ocr pipeline", "Printed OCR pipeline")
                .replace("paddle text detection", "Printed OCR pipeline")}
            </Typography>
            {document.pages_total != null && document.pages_total > 0 ? (
              <Typography variant="caption" color="text.secondary">
                Page: {document.failure_page_number ?? document.active_page_number ?? 1} of{" "}
                {document.pages_total}
              </Typography>
            ) : null}
            {document.attempt_number != null && document.max_attempts != null ? (
              <Typography variant="caption" color="text.secondary">
                Attempts: {document.attempt_number} of {document.max_attempts}
              </Typography>
            ) : null}
            <Typography variant="caption" color="text.secondary">
              Error:{" "}
              {document.failure_code === "ocr_page_timeout" ||
              document.failure_message?.toLowerCase().includes("timed out")
                ? "OCR page timed out"
                : (document.failure_message ?? document.user_status_message ?? "Visual OCR failed")}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              Canonical document available: {document.canonical_view_available ? "Yes" : "No"}
            </Typography>
          </Stack>
        ) : null}

        {document.status === "native_trust_complete" ? (
          <Typography variant="caption" color="text.secondary">
            Native trust inspection complete. Visual processing is starting.
          </Typography>
        ) : null}

        {document.status === "failed" ? (
          <Stack spacing={0.5}>
            <Typography variant="caption" color="error.main">
              {document.failure_message ?? document.user_status_message ?? "Processing failed."}
            </Typography>
            {document.failure_stage || document.failure_code ? (
              <Typography variant="caption" color="text.secondary">
                Stage: {document.failure_stage ?? "—"}
                {document.failure_code ? ` · Code: ${document.failure_code}` : ""}
                {document.failure_page_number != null
                  ? ` · Page: ${document.failure_page_number}`
                  : ""}
              </Typography>
            ) : null}
            <Typography variant="caption" color="text.secondary">
              Canonical document{" "}
              {document.canonical_view_available
                ? "remains available for viewing."
                : "is not available."}
              {document.visual_processing_required
                ? " Visual processing can recover this document in a later phase."
                : ""}
            </Typography>
          </Stack>
        ) : null}

        {document.status !== "failed" &&
        document.user_status_message &&
        document.status !== "queued" &&
        document.status !== "canonicalising" &&
        document.status !== "inspecting_native" &&
        document.status !== "extracting_native" &&
        document.status !== "visual_pending" &&
        document.status !== "visual_processing" ? (
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
