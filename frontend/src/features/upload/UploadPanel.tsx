import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlined";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography,
} from "@mui/material";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";

import { ApiError } from "../../api/http";
import type { RejectedDocument, SessionLimits } from "../../contracts";
import { sessionKeys } from "../session/sessionKeys";
import { formatBytes, screenFiles, type PreliminaryRejection } from "./clientChecks";
import { uploadDocuments } from "./uploadApi";

interface UploadPanelProps {
  readonly sessionId: string;
  readonly limits: SessionLimits;
  readonly disabled?: boolean;
}

interface BatchOutcome {
  readonly acceptedCount: number;
  readonly rejected: RejectedDocument[];
  readonly preliminary: PreliminaryRejection[];
}

export function UploadPanel({ sessionId, limits, disabled = false }: UploadPanelProps) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);
  const [outcome, setOutcome] = useState<BatchOutcome | null>(null);

  const mutation = useMutation({
    mutationFn: (files: File[]) => uploadDocuments(sessionId, files),
    onSuccess: (response) => {
      queryClient.setQueryData(sessionKeys.detail(sessionId), response.session);
      setOutcome((current) => ({
        acceptedCount: response.accepted.length,
        rejected: [...(current?.rejected ?? []), ...response.rejected],
        preliminary: current?.preliminary ?? [],
      }));
    },
  });

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList || fileList.length === 0 || disabled) {
        return;
      }
      const files = Array.from(fileList);
      const screened = screenFiles(files, limits);
      setOutcome({
        acceptedCount: 0,
        rejected: [],
        preliminary: screened.rejected,
      });
      if (screened.acceptable.length > 0) {
        mutation.mutate(screened.acceptable);
      }
    },
    [disabled, limits, mutation],
  );

  const onDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragActive(false);
      handleFiles(event.dataTransfer.files);
    },
    [handleFiles],
  );

  const onInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      handleFiles(event.target.files);
      event.target.value = "";
    },
    [handleFiles],
  );

  const acceptAttr = useMemo(() => limits.supported_extensions.join(","), [limits]);

  const errorMessage =
    mutation.error instanceof ApiError
      ? mutation.error.message
      : mutation.error
        ? "The upload could not be completed."
        : null;

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h2" component="h2">
            Upload documents
          </Typography>

          <Box
            role="button"
            tabIndex={disabled ? -1 : 0}
            aria-disabled={disabled}
            aria-label="Upload files by clicking or dropping them here"
            onClick={() => !disabled && inputRef.current?.click()}
            onKeyDown={(event) => {
              if (!disabled && (event.key === "Enter" || event.key === " ")) {
                event.preventDefault();
                inputRef.current?.click();
              }
            }}
            onDragOver={(event) => {
              event.preventDefault();
              if (!disabled) {
                setDragActive(true);
              }
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={onDrop}
            sx={{
              border: "2px dashed",
              borderColor: dragActive ? "primary.main" : "divider",
              borderRadius: 2,
              p: 4,
              textAlign: "center",
              cursor: disabled ? "not-allowed" : "pointer",
              bgcolor: dragActive ? "action.hover" : "transparent",
              opacity: disabled ? 0.6 : 1,
              transition: "border-color 120ms, background-color 120ms",
            }}
          >
            <UploadFileIcon fontSize="large" color="action" />
            <Typography variant="body1" sx={{ mt: 1 }}>
              Drag and drop files here, or click to browse
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Supported: {limits.supported_extensions.join(", ")} · up to{" "}
              {formatBytes(limits.max_single_file_bytes)} per file · {limits.max_files_per_session}{" "}
              files per session
            </Typography>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept={acceptAttr}
              hidden
              disabled={disabled}
              onChange={onInputChange}
              data-testid="upload-input"
            />
          </Box>

          <Button
            variant="contained"
            startIcon={<UploadFileIcon />}
            onClick={() => inputRef.current?.click()}
            disabled={disabled || mutation.isPending}
          >
            {mutation.isPending ? "Uploading..." : "Choose files"}
          </Button>

          {errorMessage ? (
            <Alert severity="error" role="alert">
              {errorMessage}
            </Alert>
          ) : null}

          {outcome ? <UploadOutcome outcome={outcome} pending={mutation.isPending} /> : null}
        </Stack>
      </CardContent>
    </Card>
  );
}

function UploadOutcome({ outcome, pending }: { outcome: BatchOutcome; pending: boolean }) {
  const hasRejections = outcome.rejected.length > 0 || outcome.preliminary.length > 0;
  if (!hasRejections && outcome.acceptedCount === 0 && !pending) {
    return null;
  }
  return (
    <Box>
      {outcome.acceptedCount > 0 ? (
        <Alert severity="success" icon={<CheckCircleIcon />} sx={{ mb: hasRejections ? 1 : 0 }}>
          {outcome.acceptedCount} file{outcome.acceptedCount === 1 ? "" : "s"} accepted.
        </Alert>
      ) : null}
      {hasRejections ? (
        <Alert severity="warning" icon={<ErrorOutlineIcon />}>
          <Typography variant="body2" sx={{ fontWeight: 600 }}>
            Some files were rejected
          </Typography>
          <List dense disablePadding>
            {outcome.preliminary.map((item) => (
              <ListItem key={`pre-${item.file.name}`} disableGutters>
                <ListItemIcon sx={{ minWidth: 28 }}>
                  <ErrorOutlineIcon fontSize="small" color="warning" />
                </ListItemIcon>
                <ListItemText primary={item.file.name} secondary={item.reason} />
              </ListItem>
            ))}
            {outcome.rejected.map((item, index) => (
              <ListItem key={`srv-${item.input_index}-${index}`} disableGutters>
                <ListItemIcon sx={{ minWidth: 28 }}>
                  <ErrorOutlineIcon fontSize="small" color="warning" />
                </ListItemIcon>
                <ListItemText
                  primary={item.display_filename ?? `File #${item.input_index + 1}`}
                  secondary={item.message}
                />
              </ListItem>
            ))}
          </List>
        </Alert>
      ) : null}
    </Box>
  );
}
