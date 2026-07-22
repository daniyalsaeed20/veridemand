import { Alert, Divider, FormControlLabel, Stack, Switch, Typography } from "@mui/material";

import type { NativeDocumentSummary, NativePageResult } from "../../contracts";

export interface NativeInspectionPanelProps {
  readonly summary: NativeDocumentSummary;
  readonly page: NativePageResult | undefined;
  readonly nativeOverlayEnabled: boolean;
  readonly onToggleNativeOverlay: () => void;
  readonly overlaysDisabled?: boolean;
}

function displayValue(value: string | number | null | undefined): string {
  return value == null ? "—" : String(value);
}

export function NativeInspectionPanel({
  summary,
  page,
  nativeOverlayEnabled,
  onToggleNativeOverlay,
  overlaysDisabled = false,
}: NativeInspectionPanelProps) {
  const accepted = page?.decision === "accepted";

  return (
    <Stack spacing={1.25} aria-label="Native inspection">
      <Typography variant="subtitle2">Native inspection</Typography>
      <Typography variant="body2">
        Document source policy: {displayValue(summary.document_source_policy)}
      </Typography>
      <Alert severity="info">Visual agreement not yet evaluated.</Alert>
      <Alert severity="info">Extraction order is provisional.</Alert>

      {page ? (
        <>
          <Divider />
          <Typography variant="body2">
            Page {page.page_number} · Source mode: {page.source_mode} · Decision: {page.decision}
          </Typography>
          <Typography variant="body2">
            Trust score: {displayValue(page.trust.native_trust_score)}
          </Typography>
          <Typography variant="body2">
            Reason codes:{" "}
            {page.trust.reason_codes?.length ? page.trust.reason_codes.join(", ") : "—"}
          </Typography>
          <Typography variant="body2">
            Native words: {page.trust.metrics.word_count} · Characters:{" "}
            {page.trust.metrics.character_count}
          </Typography>
          <Typography variant="body2">
            native_result_available: {String(page.trust.native_result_available)} ·
            visual_processing_required: {String(page.trust.visual_processing_required)}
          </Typography>

          {accepted ? (
            <>
              <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                {page.provisional_native_text}
              </Typography>
              <FormControlLabel
                control={
                  <Switch
                    checked={nativeOverlayEnabled}
                    onChange={onToggleNativeOverlay}
                    disabled={overlaysDisabled}
                    slotProps={{ input: { "aria-label": "Show native word boxes" } }}
                  />
                }
                label="Show native word boxes"
              />
              {overlaysDisabled ? (
                <Typography variant="caption" color="text.secondary">
                  Native PDF boxes are disabled because this page has a dimension mismatch.
                </Typography>
              ) : null}
            </>
          ) : null}
          {page.decision === "rejected" ? (
            <Alert severity="warning">
              The native text layer was rejected. This page requires visual processing in Phase 4.
            </Alert>
          ) : null}
          {page.source_mode === "image_authority" || page.decision === "absent" ? (
            <Alert severity="info">
              No native text is available. This page requires visual processing.
            </Alert>
          ) : null}
        </>
      ) : null}
    </Stack>
  );
}
