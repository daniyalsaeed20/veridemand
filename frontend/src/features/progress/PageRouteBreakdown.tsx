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

export function PageRouteBreakdown({ snapshot }: PageRouteBreakdownProps) {
  return (
    <Box aria-label="Page route breakdown" sx={{ mt: 1 }}>
      <Typography variant="subtitle2" gutterBottom>
        Route breakdown
      </Typography>
      <Stack spacing={0.25}>
        <ValueOrSkeleton value={snapshot.native_pages_retained} label="Native pages retained" />
        <ValueOrSkeleton
          value={snapshot.embedded_ocr_pages_verified}
          label="Embedded OCR verified"
        />
        <ValueOrSkeleton value={snapshot.targeted_repair_pages_selected} label="Targeted repairs" />
        <ValueOrSkeleton value={snapshot.full_ocr_pages_selected} label="Full OCR required" />
        <ValueOrSkeleton value={snapshot.full_ocr_pages_completed} label="Full OCR completed" />
        <ValueOrSkeleton value={snapshot.full_ocr_pages_remaining} label="Full OCR remaining" />
      </Stack>
    </Box>
  );
}
