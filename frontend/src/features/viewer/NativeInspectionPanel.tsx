import { Alert, Divider, FormControlLabel, Stack, Switch, Typography } from "@mui/material";

import type {
  DuplicateLayerEvidence,
  NativeDocumentSummary,
  NativePageResult,
} from "../../contracts";

export interface NativeInspectionPanelProps {
  readonly summary: NativeDocumentSummary;
  readonly page: NativePageResult | undefined;
  readonly nativeOverlayEnabled: boolean;
  readonly onToggleNativeOverlay: () => void;
  readonly overlaysDisabled?: boolean;
}

function displayValue(value: string | number | boolean | null | undefined): string {
  return value == null ? "—" : String(value);
}

function DuplicateEvidencePanel({ evidence }: { evidence: DuplicateLayerEvidence }) {
  const rules = [...(evidence.path_a_rules ?? []), ...(evidence.path_b_rules ?? [])];
  return (
    <Stack spacing={0.75} data-testid="duplicate-layer-evidence">
      <Typography variant="body2">Duplicate-layer decision</Typography>
      <Typography variant="body2">Policy version: {evidence.policy_version}</Typography>
      <Typography variant="body2">Selected path: {evidence.selected_path}</Typography>
      <Typography variant="body2">
        Hard rejection caused by duplicate layer: {evidence.hard_rejection ? "Yes" : "No"}
      </Typography>
      {rules.map((rule) => (
        <Typography
          key={rule.rule_id}
          variant="caption"
          component="div"
          data-testid={`dup-rule-${rule.rule_id}`}
          sx={{ fontFamily: "monospace", whiteSpace: "pre-wrap" }}
        >
          {rule.metric_name}: {displayValue(rule.actual_value)} {rule.operator}{" "}
          {displayValue(rule.threshold)} · {rule.mandatory ? "mandatory" : "informational"} ·{" "}
          {rule.passed ? "pass" : "fail"} · path={rule.applies_to_path}
        </Typography>
      ))}
    </Stack>
  );
}

export function NativeInspectionPanel({
  summary,
  page,
  nativeOverlayEnabled,
  onToggleNativeOverlay,
  overlaysDisabled = false,
}: NativeInspectionPanelProps) {
  const accepted = page?.decision === "accepted";
  const evidence = page?.trust.metrics.duplicate_layer_evidence;
  const overallHard = page?.trust.hard_rejection ?? false;
  const duplicateHard = page?.trust.duplicate_hard_rejection ?? false;
  const overallCause =
    page?.trust.reason_codes?.filter((c) => c !== "excessive_near_overprint_duplicates")?.[0] ??
    page?.trust.reason_codes?.[0] ??
    "—";

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
          <Typography variant="body2" data-testid="overall-native-hard-rejection">
            Overall native hard rejection: {String(overallHard)}
            {overallHard ? ` · Cause: ${overallCause}` : ""}
          </Typography>
          <Typography variant="body2" data-testid="duplicate-layer-hard-rejection">
            Duplicate-layer hard rejection: {String(duplicateHard)} · Selected duplicate path:{" "}
            {displayValue(page.trust.metrics.hard_rule_path)}
          </Typography>
          <Typography variant="body2">
            Duplication quality score:{" "}
            {displayValue(page.trust.metrics.components?.duplication_quality_score)}
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
          {evidence ? <DuplicateEvidencePanel evidence={evidence} /> : null}
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
