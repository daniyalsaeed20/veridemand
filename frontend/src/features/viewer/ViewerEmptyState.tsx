// Placeholder shown in the viewer column whenever there is nothing to render:
// no document selected, canonicalisation still in progress, or a load
// failure. Never implies extraction results are available (Phase 2 performs
// no extraction).

import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlined";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import { Box, Stack, Typography } from "@mui/material";
import type { ReactNode } from "react";

export type ViewerEmptyStateVariant = "no_selection" | "not_ready" | "failed" | "load_error";

const DEFAULTS: Record<ViewerEmptyStateVariant, { title: string; description: string }> = {
  no_selection: {
    title: "No document selected",
    description: "Choose a document from the queue to open its canonical document.",
  },
  not_ready: {
    title: "Canonical document not ready",
    description: "Extraction has not started. The canonical view will appear once ready.",
  },
  failed: {
    title: "Canonical document unavailable",
    description: "Canonicalisation failed for this document, so no viewer preview is available.",
  },
  load_error: {
    title: "Could not load the canonical document",
    description: "The document could not be fetched. Try selecting it again.",
  },
};

const ICONS: Record<ViewerEmptyStateVariant, ReactNode> = {
  no_selection: <DescriptionOutlinedIcon fontSize="large" color="disabled" />,
  not_ready: <HourglassEmptyIcon fontSize="large" color="disabled" />,
  failed: <ErrorOutlineIcon fontSize="large" color="error" />,
  load_error: <ErrorOutlineIcon fontSize="large" color="error" />,
};

export interface ViewerEmptyStateProps {
  readonly variant: ViewerEmptyStateVariant;
  readonly title?: string;
  readonly description?: string;
}

export function ViewerEmptyState({ variant, title, description }: ViewerEmptyStateProps) {
  const defaults = DEFAULTS[variant];
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        minHeight: 360,
        p: 4,
        textAlign: "center",
      }}
    >
      <Stack spacing={1.5} sx={{ alignItems: "center", maxWidth: 360 }}>
        {ICONS[variant]}
        <Typography variant="h3" component="p">
          {title ?? defaults.title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {description ?? defaults.description}
        </Typography>
      </Stack>
    </Box>
  );
}
