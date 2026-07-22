import { Chip } from "@mui/material";

export interface OcrConfidenceBadgeProps {
  readonly score: number | null | undefined;
  readonly lowThreshold?: number;
}

export function OcrConfidenceBadge({ score, lowThreshold = 0.75 }: OcrConfidenceBadgeProps) {
  if (score == null) {
    return <Chip size="small" label="OCR conf —" variant="outlined" />;
  }
  const low = score < lowThreshold;
  return (
    <Chip
      size="small"
      label={`OCR conf ${score.toFixed(2)}`}
      color={low ? "warning" : "default"}
      variant="outlined"
    />
  );
}
