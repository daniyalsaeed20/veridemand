import { Box, Skeleton, Stack, Typography } from "@mui/material";

import type { ProgressSnapshotInput } from "./deriveLiveProgress";

interface PageRouteBreakdownProps {
  readonly snapshot: ProgressSnapshotInput;
}

function ValueOrSkeleton({
  value,
  label,
}: {
  readonly value: number | null | undefined;
  readonly label: string;
}) {
  return (
    <Typography variant="body2" color="text.secondary">
      {label}:{" "}
      {value == null ? (
        <Skeleton variant="text" width={32} sx={{ display: "inline-block" }} />
      ) : (
        value
      )}
    </Typography>
  );
}

function exclusiveSum(hist: NonNullable<ProgressSnapshotInput["final_route_histogram"]>): number {
  return (
    (hist.digital_native_pages ?? 0) +
    (hist.embedded_ocr_verified_pages ?? 0) +
    (hist.embedded_ocr_targeted_repair_pages ?? 0) +
    (hist.full_visual_ocr_pages ?? 0) +
    (hist.visual_no_text_pages ?? 0) +
    (hist.vision_reserved_pending_phase_6_pages ?? 0) +
    (hist.page_failed_pages ?? 0) +
    (hist.page_cancelled_pages ?? 0) +
    (hist.pending_pages ?? 0)
  );
}

export function PageRouteBreakdown({ snapshot }: PageRouteBreakdownProps) {
  const hist = snapshot.final_route_histogram ?? null;
  const pagesTotal = snapshot.document_pages_total ?? null;
  const sum = hist != null ? exclusiveSum(hist) : null;
  const terminalSum = hist == null ? null : sum! - (hist.pending_pages ?? 0);
  const sumsMatch = hist != null && pagesTotal != null && sum != null && sum === pagesTotal;

  return (
    <Box aria-label="Page route breakdown" sx={{ mt: 1 }}>
      <Typography variant="subtitle2" gutterBottom>
        Exclusive route histogram
      </Typography>
      <Stack spacing={0.25}>
        <ValueOrSkeleton value={hist?.digital_native_pages} label="Digital native" />
        <ValueOrSkeleton value={hist?.embedded_ocr_verified_pages} label="Embedded OCR verified" />
        <ValueOrSkeleton value={hist?.embedded_ocr_targeted_repair_pages} label="Targeted repair" />
        <ValueOrSkeleton value={hist?.full_visual_ocr_pages} label="Full visual OCR" />
        <ValueOrSkeleton value={hist?.visual_no_text_pages} label="Visual no text" />
        <ValueOrSkeleton
          value={hist?.vision_reserved_pending_phase_6_pages}
          label="Reserved for vision processing"
        />
        <ValueOrSkeleton value={hist?.page_failed_pages} label="Page failed" />
        <Typography variant="body2" color="text.secondary">
          Exclusive sum:{" "}
          {sum == null ? (
            <Skeleton variant="text" width={32} sx={{ display: "inline-block" }} />
          ) : (
            <>
              {sum}
              {pagesTotal != null ? ` / ${pagesTotal} pages` : null}
              {sumsMatch ? " (matches)" : null}
              {terminalSum != null ? ` · terminal ${terminalSum}` : null}
            </>
          )}
        </Typography>
      </Stack>

      <Typography variant="subtitle2" gutterBottom sx={{ mt: 1.5 }}>
        Selection diagnostics (overlapping)
      </Typography>
      <Stack spacing={0.25}>
        <ValueOrSkeleton
          value={snapshot.native_pages_retained}
          label="Native pages retained (includes embedded)"
        />
        <ValueOrSkeleton
          value={snapshot.embedded_ocr_pages_verified}
          label="Embedded OCR verified"
        />
        <ValueOrSkeleton
          value={snapshot.targeted_repair_pages_selected}
          label="Targeted repairs selected"
        />
        <ValueOrSkeleton value={snapshot.full_ocr_pages_selected} label="Full OCR selected" />
        <ValueOrSkeleton value={snapshot.full_ocr_pages_completed} label="Full OCR completed" />
        <ValueOrSkeleton value={snapshot.full_ocr_pages_remaining} label="Full OCR remaining" />
      </Stack>
    </Box>
  );
}
