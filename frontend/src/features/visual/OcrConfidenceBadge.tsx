import { Chip, Stack, Typography } from "@mui/material";

export interface OcrConfidenceBadgeProps {
  readonly score: number | null | undefined;
  readonly lowThreshold?: number;
  /** Recognition confidence only — never displayed as transcript accuracy. */
  readonly qualityStatus?: string | null;
  readonly fallbackUsed?: boolean;
  readonly selectedPass?: string | null;
  readonly primaryLimitSide?: number | null;
  readonly fallbackLimitSide?: number | null;
  readonly lowConfidenceCount?: number | null;
}

export function OcrConfidenceBadge({
  score,
  lowThreshold = 0.75,
  qualityStatus,
  fallbackUsed,
  selectedPass,
  primaryLimitSide,
  fallbackLimitSide,
  lowConfidenceCount,
}: OcrConfidenceBadgeProps) {
  const low = score != null && score < lowThreshold;
  return (
    <Stack spacing={0.5} data-testid="ocr-quality-summary">
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }} useFlexGap>
        <Chip
          size="small"
          label={
            score == null ? "OCR recognition conf —" : `OCR recognition conf ${score.toFixed(2)}`
          }
          color={low ? "warning" : "default"}
          variant="outlined"
        />
        {qualityStatus ? (
          <Chip
            size="small"
            label={`OCR quality ${qualityStatus}`}
            color={
              qualityStatus === "good"
                ? "success"
                : qualityStatus === "failed" || qualityStatus === "insufficient"
                  ? "error"
                  : qualityStatus === "low_quality"
                    ? "warning"
                    : "default"
            }
            variant="outlined"
            data-testid="ocr-quality-status"
          />
        ) : null}
        {fallbackUsed ? (
          <Chip
            size="small"
            label="Fallback used"
            color="info"
            variant="outlined"
            data-testid="ocr-fallback-used"
          />
        ) : null}
        {lowConfidenceCount != null && lowConfidenceCount > 0 ? (
          <Chip
            size="small"
            label={`Low-confidence items ${lowConfidenceCount}`}
            variant="outlined"
          />
        ) : null}
      </Stack>
      {(primaryLimitSide != null || selectedPass) && (
        <Typography variant="caption" color="text.secondary" data-testid="ocr-pass-labels">
          {primaryLimitSide != null ? `Primary pass: ${primaryLimitSide}` : null}
          {fallbackLimitSide != null ? ` · Fallback pass: ${fallbackLimitSide}` : null}
          {selectedPass
            ? ` · Selected pass: ${selectedPass === "fallback" ? "Fallback" : "Primary"}`
            : null}
        </Typography>
      )}
    </Stack>
  );
}
