import { Alert, FormControlLabel, Stack, Switch, Typography } from "@mui/material";

import type { VisualDocumentSummary, VisualPageResult } from "../../contracts";
import { OcrConfidenceBadge } from "./OcrConfidenceBadge";
import { VisualPageStatus } from "./VisualPageStatus";
import { VisualTextPanel } from "./VisualTextPanel";
import { VisualWarnings } from "./VisualWarnings";

export interface VisualInspectionPanelProps {
  readonly summary: VisualDocumentSummary;
  readonly page: VisualPageResult | undefined;
  readonly loading?: boolean;
  readonly ocrLineOverlayEnabled: boolean;
  readonly ocrWordOverlayEnabled: boolean;
  readonly onToggleOcrLineOverlay: () => void;
  readonly onToggleOcrWordOverlay: () => void;
  readonly overlaysDisabled?: boolean;
}

export function VisualInspectionPanel({
  summary,
  page,
  loading,
  ocrLineOverlayEnabled,
  ocrWordOverlayEnabled,
  onToggleOcrLineOverlay,
  onToggleOcrWordOverlay,
  overlaysDisabled = false,
}: VisualInspectionPanelProps) {
  return (
    <Stack spacing={1.5} data-testid="visual-inspection-panel">
      <Typography variant="subtitle1">Printed visual OCR</Typography>
      <Alert severity="info">Printed OCR result — provisional</Alert>
      <Alert severity="warning">Handwriting has not yet been assessed.</Alert>
      <Alert severity="warning">Reading order is preliminary.</Alert>
      {loading ? <Typography variant="body2">Loading visual results…</Typography> : null}
      <VisualPageStatus
        status={summary.visual_processing_status}
        pagesCompleted={summary.pages_completed}
        pagesTotal={summary.page_count}
        sourcePolicy={summary.document_source_policy}
      />
      <FormControlLabel
        control={
          <Switch
            checked={ocrLineOverlayEnabled}
            onChange={onToggleOcrLineOverlay}
            disabled={overlaysDisabled}
            size="small"
          />
        }
        label="Show OCR line boxes"
      />
      <FormControlLabel
        control={
          <Switch
            checked={ocrWordOverlayEnabled}
            onChange={onToggleOcrWordOverlay}
            disabled={overlaysDisabled}
            size="small"
          />
        }
        label="Show OCR word boxes"
      />
      {page ? (
        <>
          <Typography variant="body2">
            Source:{" "}
            {page.source_mode === "native_authority" ? "Native PDF text" : "Printed visual OCR"}
          </Typography>
          <Typography variant="body2">
            Lines: {page.line_count} · Words: {page.word_count}
          </Typography>
          <OcrConfidenceBadge score={page.average_recognition_score} />
          <Typography variant="body2">
            Preprocessing: {page.preprocessing_variant ?? "n/a"}
            {page.fallback_used ? " (fallback used)" : ""}
          </Typography>
          <VisualWarnings warnings={page.warnings ?? []} />
          <VisualTextPanel page={page} />
        </>
      ) : null}
    </Stack>
  );
}
