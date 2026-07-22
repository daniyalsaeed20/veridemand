// Page navigation controls for the canonical viewer.
//
// Named, keyboard-operable controls (native <button>/<input> elements) with
// an `aria-live` region announcing the current page for screen readers.

import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { IconButton, Stack, TextField, Typography } from "@mui/material";
import { useEffect, useState, type ChangeEvent, type KeyboardEvent } from "react";

export interface PageNavigationProps {
  readonly pageNumber: number;
  readonly pageCount: number;
  readonly onPageNumberChange: (pageNumber: number) => void;
  readonly disabled?: boolean;
}

export function PageNavigation({
  pageNumber,
  pageCount,
  onPageNumberChange,
  disabled = false,
}: PageNavigationProps) {
  const [draft, setDraft] = useState(String(pageNumber));

  useEffect(() => {
    setDraft(String(pageNumber));
  }, [pageNumber]);

  const clamp = (value: number) => Math.min(pageCount, Math.max(1, value));

  const commitDraft = () => {
    const parsed = Number.parseInt(draft, 10);
    if (Number.isFinite(parsed)) {
      onPageNumberChange(clamp(parsed));
    } else {
      setDraft(String(pageNumber));
    }
  };

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    setDraft(event.target.value.replace(/[^0-9]/g, ""));
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commitDraft();
    }
  };

  return (
    <Stack direction="row" spacing={1} sx={{ alignItems: "center", position: "relative" }}>
      <IconButton
        aria-label="Previous page"
        size="small"
        disabled={disabled || pageNumber <= 1}
        onClick={() => onPageNumberChange(clamp(pageNumber - 1))}
      >
        <ChevronLeftIcon fontSize="small" />
      </IconButton>

      <TextField
        aria-label="Page number"
        size="small"
        value={draft}
        onChange={handleInputChange}
        onBlur={commitDraft}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        slotProps={{
          htmlInput: {
            inputMode: "numeric",
            style: { width: 40, textAlign: "center" },
            "aria-describedby": "viewer-page-count",
          },
        }}
      />

      <Typography id="viewer-page-count" variant="body2" color="text.secondary">
        of {pageCount}
      </Typography>

      <IconButton
        aria-label="Next page"
        size="small"
        disabled={disabled || pageNumber >= pageCount}
        onClick={() => onPageNumberChange(clamp(pageNumber + 1))}
      >
        <ChevronRightIcon fontSize="small" />
      </IconButton>

      {/* Screen-reader live region only; must not intercept toolbar clicks. */}
      <Typography
        aria-live="polite"
        component="span"
        sx={{
          position: "absolute",
          width: "1px",
          height: "1px",
          padding: 0,
          margin: "-1px",
          overflow: "hidden",
          clip: "rect(0, 0, 0, 0)",
          whiteSpace: "nowrap",
          border: 0,
          pointerEvents: "none",
        }}
      >
        {`Page ${pageNumber} of ${pageCount}`}
      </Typography>
    </Stack>
  );
}
