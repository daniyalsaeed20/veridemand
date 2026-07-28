import { Alert, FormControlLabel, Stack, Switch, Typography } from "@mui/material";

import type { VisualDocumentSummary, VisualPageResult } from "../../contracts";
import { OcrConfidenceBadge } from "./OcrConfidenceBadge";
import { sourceLabelForPage } from "./sourceLabels";
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

function panelTitle(page: VisualPageResult | undefined): string {
  if (!page) {
    return "Phase 4 visual processing";
  }
  return sourceLabelForPage(page);
}

function hasUsableOverlay(page: VisualPageResult | undefined): boolean {
  if (!page) {
    return false;
  }
  return (
    page.visual_result_available === true &&
    ((page.word_count ?? 0) > 0 || (page.line_count ?? 0) > 0)
  );
}

function embeddedAuthorityEmpty(page: VisualPageResult | undefined): boolean {
  if (!page) {
    return false;
  }
  return (
    page.source_mode === "embedded_ocr_authority" &&
    (!page.visual_result_available ||
      ((page.word_count ?? 0) === 0 && (page.line_count ?? 0) === 0))
  );
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
  const overlaysAvailable = hasUsableOverlay(page) && !overlaysDisabled;
  const emptyEmbedded = embeddedAuthorityEmpty(page);

  return (
    <Stack spacing={1.5} data-testid="visual-inspection-panel">
      <Typography variant="subtitle1">{panelTitle(page)}</Typography>
      <Alert severity="info">Phase 4 reconciled source decision — provisional structure</Alert>
      <Alert severity="warning">Handwriting has not yet been assessed.</Alert>
      <Alert severity="warning">Reading order is preliminary.</Alert>
      {loading ? <Typography variant="body2">Loading visual results…</Typography> : null}
      <VisualPageStatus
        status={summary.visual_processing_status}
        pagesCompleted={summary.pages_completed}
        pagesTotal={summary.document_pages_total ?? summary.page_count}
        sourcePolicy={summary.document_source_policy}
        phase3Policy={summary.phase3_provisional_document_policy}
        embeddedVerified={summary.embedded_pages_verified ?? summary.embedded_ocr_pages_verified}
        fullOcrSelected={summary.full_ocr_pages_selected ?? summary.full_ocr_pages}
        fullOcrCompleted={summary.full_ocr_pages_completed}
      />
      {summary.phase3_provisional_document_policy ? (
        <Typography variant="body2" data-testid="phase3-provisional-policy">
          Phase 3 provisional source decision: {summary.phase3_provisional_document_policy}
        </Typography>
      ) : null}
      <Typography variant="body2" data-testid="phase4-reconciled-policy">
        Phase 4 reconciled source decision: {summary.document_source_policy ?? "—"}
      </Typography>
      {emptyEmbedded ? (
        <Alert severity="error" data-testid="embedded-result-invalid">
          Embedded OCR authority is missing a verified result. Overlay boxes are unavailable. Retry
          processing if supported. The canonical PDF view remains available.
        </Alert>
      ) : null}
      <FormControlLabel
        control={
          <Switch
            checked={ocrLineOverlayEnabled}
            onChange={onToggleOcrLineOverlay}
            disabled={!overlaysAvailable}
            size="small"
          />
        }
        label="Show line boxes"
      />
      <FormControlLabel
        control={
          <Switch
            checked={ocrWordOverlayEnabled}
            onChange={onToggleOcrWordOverlay}
            disabled={!overlaysAvailable}
            size="small"
          />
        }
        label="Show word boxes"
      />
      {page ? (
        <>
          <Typography variant="body2" data-testid="visual-source-label">
            Source: {sourceLabelForPage(page)}
          </Typography>
          <Typography variant="body2" data-testid="final-page-route">
            Final route: {page.page_route ?? page.page_result_state ?? "—"}
          </Typography>
          <Typography variant="body2" data-testid="final-source-label">
            Final source label: {sourceLabelForPage(page)}
          </Typography>
          <Typography variant="body2">
            Reason codes:{" "}
            {page.route_reason_codes?.length ? page.route_reason_codes.join(", ") : "—"}
          </Typography>
          <Typography variant="body2">
            Phase 4 embedded-text verification: {page.visual_agreement_status ?? "not_evaluated"}
            {page.visual_agreement_score != null
              ? ` (score ${page.visual_agreement_score.toFixed(2)})`
              : ""}
          </Typography>
          <Typography variant="body2">
            Recognition agreement: {page.recognition_agreement_status ?? "not_evaluated"}
            {page.recognition_sample_count ? ` · samples ${page.recognition_sample_count}` : ""}
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
