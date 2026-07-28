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
        Phase 3 provisional document source policy: {displayValue(summary.document_source_policy)}
      </Typography>
      <Alert severity="info" data-testid="phase3-visual-agreement">
        Phase 3 visual agreement: not evaluated
      </Alert>
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
          <Typography variant="body2">
            hard_rejection: {String(page.trust.hard_rejection)} · duplication_score:{" "}
            {displayValue(page.trust.metrics.components?.duplication_score)}
          </Typography>
          <Typography variant="body2">
            strict_duplicate_ratio: {displayValue(page.trust.metrics.strict_duplicate_ratio)} ·
            near_overprint_duplicate_ratio:{" "}
            {displayValue(page.trust.metrics.near_overprint_duplicate_ratio)}
          </Typography>
          <Typography variant="body2">
            duplicate_layer_coverage_ratio:{" "}
            {displayValue(page.trust.metrics.duplicate_layer_coverage_ratio)} ·
            matched_near_duplicate_count:{" "}
            {displayValue(page.trust.metrics.matched_near_duplicate_count)}
          </Typography>
          <Typography variant="body2">
            dominant_offset: ({displayValue(page.trust.metrics.dominant_duplicate_offset_x)},{" "}
            {displayValue(page.trust.metrics.dominant_duplicate_offset_y)}) · support:{" "}
            {displayValue(page.trust.metrics.dominant_offset_support_ratio)} (informational)
          </Typography>
          <Typography variant="body2">
            top_k_cluster_support:{" "}
            {displayValue(page.trust.metrics.top_k_offset_cluster_support_ratio)} · clusters:{" "}
            {displayValue(page.trust.metrics.offset_cluster_count)} · dup_lines:{" "}
            {displayValue(page.trust.metrics.duplicate_line_count)} · dup_regions:{" "}
            {displayValue(page.trust.metrics.duplicate_region_count)}
          </Typography>
          <Typography variant="body2">
            hard_rule_path: {displayValue(page.trust.metrics.hard_rule_path)}
          </Typography>
          {import.meta.env.DEV && page.trust.metrics.hard_rule_explanation?.length ? (
            <Alert severity="info" sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
              {page.trust.metrics.hard_rule_explanation.join("\n")}
            </Alert>
          ) : null}

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
              {page.trust.reason_codes?.includes("excessive_near_overprint_duplicates")
                ? "The PDF contains overlapping native text layers that could not be trusted. Visual processing is required."
                : "The native text layer was rejected. This page requires visual processing in Phase 4."}
            </Alert>
          ) : null}
          {page.decision === "error" ? (
            <Alert severity="warning">
              Native text processing could not read the embedded text on this page. The canonical
              document is still available and visual processing is required.
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
